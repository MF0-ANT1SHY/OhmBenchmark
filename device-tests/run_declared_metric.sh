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

export PATH="$HOME/.local/bin:$PATH"
TC=/home/research/OhmBenchmark-toolchain/command-line-tools
export PATH="$TC/bin:$PATH"
export DEVECO_SDK_HOME="$TC/sdk"

bundle() {
  python3 - "$CASE" <<'PY'
import json,sys
print(json.load(open(f'cases/{sys.argv[1]}/case.json'))['host_app']['bundle_name'])
PY
}
BUNDLE=$(bundle)
# The module directory under haps/ differs per host: interviewapp builds `phone`, the
# weather assistant `alatus`, the rest `entry`. Read the host layout rather than guessing.
MODULE=$(python3 - "$CASE" <<'PY'
import json, sys
from pathlib import Path
case = sys.argv[1]
host = json.load(open(f'cases/{case}/case.json'))['host_app']
local = host.get('local_path', '')
cands = []
if local and Path(local).exists():
    for mod in Path(local).glob('*/src/main/module.json5'):
        cands.append(mod.parts[-4])
print(cands[0] if cands else 'entry')
PY
)
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

  local patch="$ROOT/device-tests/patches/$CASE/$variant.patch"
  if [ ! -f "$patch" ]; then
    echo "  NO HARNESS PATCH at $patch"
    echo "  -> this case needs a bench entry written from scratch; cannot measure it yet"
    return 1
  fi
  git -C "$H" apply "$patch" 2>&1 | sed 's/^/      /'
  rc=$?
  echo "  apply exit=$rc"
  [ "$rc" -eq 0 ] || { echo "  ABORT: measurement patch did not apply"; return 1; }

  # locate OhmProbe wherever this host keeps it, rather than assuming a path
  local probe
  probe=$(find "$H" -name 'OhmProbe.ets' -not -path '*/oh_modules/*' 2>/dev/null | head -1)
  if [ -z "$probe" ]; then
    echo "  ABORT: no OhmProbe.ets anywhere in the host after applying the patch;"
    echo "         the bench cannot signal state, so every run would time out"
    return 1
  fi
  echo "  OhmProbe: ${probe#$H/}"

  echo "  instrumenting:"
  python3 "$INSTRUMENTER" --hosts "$ROOT/hosts" 2>&1 | sed 's/^/  /'
  rc=${PIPESTATUS[0]}
  echo "  instrumenter exit=$rc"
  [ "$rc" -eq 0 ] || { echo "  ABORT: instrumentation failed; refusing to measure a build"
                       echo "         whose declared metric is not being counted"
                       return 1; }

  echo "  installing ohpm dependencies (some hosts need this before they compile)..."
  ( cd "$H" && timeout 1800 ohpm install --all 2>&1 | tail -1 )

  echo "  building..."
  ( cd "$H" && timeout 1800 hvigorw --mode module -p product=default -p buildMode=debug \
      assembleHap --no-daemon 2>&1 | tail -1 )

  local hap
  hap=$(find "$H" -name '*-unsigned.hap' -newermt '-20 minutes' | head -1)
  [ -n "$hap" ] || { echo "  no fresh HAP produced"; return 1; }
  timeout 300 python3 device-tests/sign_hap.py sign "$hap" "/tmp/$CASE-$variant.hap" "$BUNDLE" 2>&1 | tail -1
  timeout 120 hdc uninstall "$BUNDLE" >/dev/null 2>&1
  timeout 240 hdc install "/tmp/$CASE-$variant.hap" 2>&1 | grep -o 'install bundle successfully\|error:.*' | head -1

  for r in $(seq 1 "$REPS"); do
    echo "  --- run $r ---"
    timeout 600 python3 device-tests/collect_wsl.py "$CASE" "$variant" --run "$r" \
        --module "$MODULE" --bundle "$BUNDLE" 2>&1 | tail -2
  done
}

run_variant unfixed "$UNFIXED"
run_variant fixed "$FIXED"

echo
echo "================= SUMMARY ================="
python3 - "$CASE" "$REPS" <<'PY'
import gzip, json, re, sys, statistics
from pathlib import Path
case, reps = sys.argv[1], int(sys.argv[2])
root = Path('/home/research/OhmBenchmark-main/measurements-staging') / case
markers = ('StatementCount', 'QueryCount')
for variant in ('unfixed', 'fixed'):
    vals, times = [], []
    for r in range(1, reps + 1):
        d = root / variant / f'run{r}'
        t = d / 'trace.txt.gz'
        if t.exists():
            with gzip.open(t, 'rt', errors='replace') as f:
                blob = f.read()
            for m in markers:
                got = [int(v) for v in re.findall(m + r'\|(\d+)', blob)]
                if got:
                    vals.append(max(got)); break
        rj = d / 'result.json'
        if rj.exists():
            times.append(json.loads(rj.read_text())['elapsed_ms'])
    if vals:
        print(f"  {variant:<8} n={len(vals)}  declared-metric={vals}  median={statistics.median(vals):g}"
              f"  elapsed_median={statistics.median(times):.0f}ms")
    else:
        print(f"  {variant:<8} no declared-metric values collected")
PY
