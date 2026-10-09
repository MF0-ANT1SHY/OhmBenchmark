#!/usr/bin/env bash
# Run the 3-repetition measurement protocol for a case whose declared metric we instrument.
#
# Steps per variant:
#   1. hard-reset the host clone to the case's recorded commit for that variant
#   2. apply the repo's measurement patch for that variant (the harness entry)
#   3. apply the case's declared-metric instrumentation
#   4. build -> sign -> install
#   5. collect N runs, staged under measurements-staging/ so original evidence is untouched
#
# Usage: run_declared_metric.sh <case> <host> <unfixed-commit> <fixed-commit> <instrumenter> <reps>
set -uo pipefail

CASE=${1:?case}
HOST=${2:?host}
UNFIXED=${3:?unfixed commit}
FIXED=${4:?fixed commit}
INSTRUMENTER=${5:?instrumenter tool}
REPS=${6:-3}

ROOT=/home/research/OhmBenchmark-main
cd "$ROOT" || exit 1
H="hosts/$HOST"

# The toolchain is chosen per host. 5.1.0 applies strict ArkTS rules (arkts-no-any-unknown,
# arkts-no-implicit-return-types, arkts-no-spread) that pre-5.1 source violates: interviewapp
# declares compatibleSdkVersion 5.0.0(12) and shows 38 such errors under 5.1.0 while building
# unmodified under 5.0.5. See device-tests/host_toolchain.txt.
HOST_NAME=$(python3 -c "import json,sys;from pathlib import Path;print(Path(json.loads(Path(f'cases/{sys.argv[1]}/case.json').read_text())['host_app'].get('local_path','')).name)" "$CASE")
TC_VERSION=$(awk -v h="$HOST_NAME" '$1==h {print $2}' "$ROOT/device-tests/host_toolchain.txt" 2>/dev/null | head -1)
[ -n "$TC_VERSION" ] || TC_VERSION=5.1.0
# shellcheck disable=SC1090
source "$ROOT/device-tests/toolchain.sh" "$TC_VERSION"
echo "host: $HOST_NAME   toolchain: $TC_VERSION"

bundle() {
  python3 - "$CASE" <<'PY'
import json,sys
print(json.load(open(f'cases/{sys.argv[1]}/case.json'))['host_app']['bundle_name'])
PY
}
BUNDLE=$(bundle)
ABILITY=$(python3 "$ROOT/device-tests/host_module.py" "$CASE" --ability)
[ -n "$ABILITY" ] || { echo "ABORT: could not resolve the ability"; exit 1; }
echo "ability: $ABILITY"
SELF_INSTALL=0
case "$INSTRUMENTER" in
  self-installing:*)
    SELF_INSTALL=1
    INSTRUMENTER="${INSTRUMENTER#self-installing:}"
    ;;
esac
# The metric may come from a different place than the harness came from. A case whose count is
# logged by the app to its diag file sets SUMMARY_SOURCE=diag:<key> while its harness is
# installed by the instrumenter above.
SUMMARY_SOURCE="$SUMMARY_SOURCE"
MODULE=$(python3 "$ROOT/device-tests/host_module.py" "$CASE")
[ -n "$MODULE" ] || { echo "ABORT: could not resolve the host module"; exit 1; }
echo "host module: $MODULE" 

run_variant() {
  local variant=$1 commit=$2
  echo "================= $CASE / $variant (commit $commit) ================="
  # Clean FIRST, then apply the harness: the harness files are untracked additions from
  # the measurement patch, so a later `git clean -fd` would delete them again.
  git -C "$H" checkout --force "$commit" 2>&1 | tail -2
  local rc=$?
  echo "  checkout exit=$rc"
  [ "$rc" -eq 0 ] || { echo "  ABORT: checkout failed"; return 1; }

  git -C "$H" clean -fd 2>&1 | tail -3
  echo "  clean exit=$?"
  echo "  HEAD: $(git -C "$H" rev-parse --short HEAD)"
  echo "  dirty after reset: $(git -C "$H" status --porcelain | wc -l) file(s)"
  if [ "$(git -C "$H" status --porcelain | wc -l)" -ne 0 ]; then
    echo "  ABORT: the tree is not clean after checkout+clean; the reset is not doing its job"
    git -C "$H" status --porcelain | head -5 | sed 's/^/      /'
    return 1
  fi

  case "$SELF_INSTALL" in
    1)
      echo "  no harness patch for this host; the instrumenter installs the harness itself"
      ;;
    *)
      local patch="$ROOT/device-tests/patches/$CASE/$variant.patch"
      if [ ! -f "$patch" ]; then
        echo "  NO HARNESS PATCH at $patch"
        echo "  -> pass self-installing:<tool> if that tool creates the harness, otherwise"
        echo "     this case needs a bench entry written from scratch"
        return 1
      fi
      git -C "$H" apply "$patch" 2>&1 | sed 's/^/      /'
      rc=$?
      echo "  apply exit=$rc"
      [ "$rc" -eq 0 ] || { echo "  ABORT: measurement patch did not apply"; return 1; }
      ;;
  esac


  case "$INSTRUMENTER" in
    result:*)
      echo "  no instrumentation needed: the declared metric is the bench's own result field"
      ;;
    diag:*)
      echo "  no further instrumentation: the declared metric is read from the app's diag log"
      ;;
    *)
      echo "  instrumenting:"
      python3 "$INSTRUMENTER" --hosts "$ROOT/hosts" 2>&1 | sed 's/^/  /'
      rc=${PIPESTATUS[0]}
      echo "  instrumenter exit=$rc"
      [ "$rc" -eq 0 ] || { echo "  ABORT: instrumentation failed; refusing to measure a build"
                           echo "         whose declared metric is not being counted"
                           return 1; }
      ;;
  esac


  # A harness may name its file anything; what matters is that something writes the state file
  # the collector waits for. Checking for the capability rather than a filename keeps harnesses
  # like the wanharmony progress-log one (which signals from OhmLogCount.ets) usable.
  local probe
  probe=$(grep -rl 'ohm-status.json' "$H" --include='*.ets' 2>/dev/null \
          | grep -v oh_modules | head -1)
  if [ -z "$probe" ]; then
    echo "  ABORT: nothing in the host writes ohm-status.json, so the collector would wait"
    echo "         forever; the harness is not installed"
    return 1
  fi
  echo "  state writer: ${probe#$H/}"

  echo "  installing ohpm dependencies (some hosts need this before they compile)..."
  ( cd "$H" && timeout 1800 ohpm install --all 2>&1 | tail -1 )

  echo "  building..."
  ( cd "$H" && timeout 1800 hvigorw --mode module -p product=default -p buildMode=debug \
      assembleHap --no-daemon 2>&1 | tail -1 )

  # Prefer the HAP whose output directory matches the module the device installs under
  # (phone/entry/alatus). Do NOT filter by mtime: hvigor leaves an unchanged HAP's timestamp
  # alone, so a successful build can produce no "fresh" file at all.
  local hap
  hap=$(find "$H" -name "*-unsigned.hap" -path "*$MODULE*" -not -path '*/oh_modules/*' \
        2>/dev/null | head -1)
  if [ -z "$hap" ]; then
    # fall back to any artifact this host produces, newest first
    hap=$(find "$H" -name '*-unsigned.hap' -not -path '*/oh_modules/*' -printf '%T@ %p\n' \
          2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
  fi
  [ -n "$hap" ] || { echo "  ABORT: no unsigned HAP anywhere in $H"; return 1; }
  echo "  hap: ${hap#$H/}"
  # the HAP must contain the ability the collector will start, or every run will fail with
  # "The specified ability does not exist"
  if command -v unzip >/dev/null 2>&1; then
    unzip -p "$hap" module.json 2>/dev/null | grep -q "$ABILITY" \
      || echo "  WARNING: module.json in this HAP does not mention $ABILITY"
  fi
  timeout 300 python3 device-tests/sign_hap.py sign "$hap" "/tmp/$CASE-$variant.hap" "$BUNDLE" 2>&1 | tail -1
  timeout 120 hdc uninstall "$BUNDLE" >/dev/null 2>&1
  timeout 240 hdc install "/tmp/$CASE-$variant.hap" 2>&1 | grep -o 'install bundle successfully\|error:.*' | head -1

  for r in $(seq 1 "$REPS"); do
    echo "  --- run $r ---"
    timeout 600 python3 device-tests/collect_wsl.py "$CASE" "$variant" --run "$r" \
        --module "$MODULE" --bundle "$BUNDLE" --ability "$ABILITY" 2>&1 | tail -2
  done
}

run_variant unfixed "$UNFIXED"
run_variant fixed "$FIXED"

echo
echo "================= SUMMARY ================="
python3 - "$CASE" "$REPS" "${SUMMARY_SOURCE:-$INSTRUMENTER}" <<'PY'
import gzip, json, re, sys, statistics
from pathlib import Path
case, reps, instrumenter = sys.argv[1], int(sys.argv[2]), sys.argv[3]
root = Path('/home/research/OhmBenchmark-main/measurements-staging') / case
use_result = instrumenter.startswith('result:')
use_diag = instrumenter.startswith('diag:')
diag_key = instrumenter.split(':', 1)[1] if use_diag else ''
for variant in ('unfixed', 'fixed'):
    vals, times = [], []
    for r in range(1, reps + 1):
        d = root / variant / f'run{r}'
        rj = d / 'result.json'
        res = json.loads(rj.read_text()) if rj.exists() else {}
        if use_diag:
            dg = d / 'diag.json'
            if dg.exists():
                # take the LAST checkpoint carrying the key: earlier checkpoints log the same
                # key before the work happens (parseTotal=0 before routing), so matching every
                # line would report both the pre- and post-measurement readings
                got = None
                for line in dg.read_text(encoding='utf-8').splitlines():
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    for kv in str(rec.get('v', '')).split():
                        if kv.startswith(diag_key + '='):
                            got = int(kv.split('=', 1)[1])
                if got is not None:
                    vals.append(got)
        elif use_result:
            if 'result' in res:
                vals.append(res['result'])
        else:
            t = d / 'trace.txt.gz'
            if t.exists():
                with gzip.open(t, 'rt', errors='replace') as f:
                    blob = f.read()
                # any OHMB/<Name>|<int> marker, so new instrumenters need no edit here
                found = [(m, int(v)) for m, v in re.findall(r'OHMB/([A-Za-z]+)\|(\d+)', blob)]
                if found:
                    name = found[0][0]
                    vals.append(max(v for n, v in found if n == name))
        if 'elapsed_ms' in res:
            times.append(res['elapsed_ms'])
    if vals:
        print(f"  {variant:<8} n={len(vals)}  declared-metric={vals}  median={statistics.median(vals):g}"
              f"  elapsed_median={statistics.median(times):.0f}ms")
    else:
        print(f"  {variant:<8} no declared-metric values collected")
PY
