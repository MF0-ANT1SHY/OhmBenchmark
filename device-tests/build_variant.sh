#!/usr/bin/env bash
# Build-only variant pipeline (no install/collect): checkout -> clean -> patch -> instrument -> build -> sign.
# Usage: build_variant.sh <case> <host> <variant> <commit> <instrumenter|none>
set -uo pipefail
CASE=$1; HOST=$2; VARIANT=$3; COMMIT=$4; INSTRUMENTER=${5:-none}
ROOT=/home/research/OhmBenchmark-main
cd "$ROOT" || exit 1
H="hosts/$HOST"
HOST_NAME=$(python3 -c "import json;from pathlib import Path;print(Path(json.loads(Path('cases/$CASE/case.json').read_text())['host_app'].get('local_path','')).name)")
TC_VERSION=$(awk -v h="$HOST_NAME" '$1==h {print $2}' device-tests/host_toolchain.txt | head -1)
[ -n "$TC_VERSION" ] || TC_VERSION=5.1.0
source device-tests/toolchain.sh "$TC_VERSION"
BUNDLE=$(python3 -c "import json;print(json.load(open('cases/$CASE/case.json'))['host_app']['bundle_name'])")
echo "== $CASE/$VARIANT @ $COMMIT (toolchain $TC_VERSION)"
git -C "$H" checkout --force "$COMMIT" 2>&1 | tail -1 || exit 1
git -C "$H" clean -fd 2>&1 | tail -1
patch="device-tests/patches/$CASE/$VARIANT.patch"
[ -f "$patch" ] && { git -C "$H" apply "$ROOT/$patch" || { echo "PATCH FAILED"; exit 1; }; }
if [ "$INSTRUMENTER" != "none" ]; then
  python3 "$INSTRUMENTER" --hosts "$ROOT/hosts" || { echo "INSTRUMENT FAILED"; exit 1; }
fi
( cd "$H" && timeout 1800 ohpm install --all 2>&1 | tail -1 )
( cd "$H" && timeout 1800 hvigorw --mode module -p product=default -p buildMode=debug assembleHap --no-daemon 2>&1 | tail -3 )
MODULE=$(python3 device-tests/host_module.py "$CASE")
hap=$(find "$H" -name "*-unsigned.hap" -path "*$MODULE*" -not -path '*/oh_modules/*' | head -1)
[ -n "$hap" ] || hap=$(find "$H" -name '*-unsigned.hap' -not -path '*/oh_modules/*' -printf '%T@ %p\n' | sort -rn | head -1 | cut -d' ' -f2-)
[ -n "$hap" ] || { echo "NO HAP"; exit 1; }
timeout 300 python3 device-tests/sign_hap.py sign "$hap" "/tmp/$CASE-$VARIANT.hap" "$BUNDLE" | tail -1
echo "SIGNED /tmp/$CASE-$VARIANT.hap"
