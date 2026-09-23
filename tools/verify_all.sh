#!/usr/bin/env bash
# Rebuild every case's unfixed and fixed commits and record PASS/FAIL.
# Usage: bash tools/verify_all.sh [case-id ...]   (no args = all cases)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/toolchain/command-line-tools/bin:$PATH"
export DEVECO_SDK_HOME="$ROOT/toolchain/command-line-tools/sdk"
RESULT_FILE="$ROOT/build_results.jsonl"
: > "$RESULT_FILE"

ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then
  ids=($(ls "$ROOT/cases"))
fi

build_commit() { # $1 host repo, $2 commit, $3 case id, $4 label
  local repo="$ROOT/hosts/$1" commit="$2" cid="$3" label="$4" out status
  git -C "$repo" checkout -q "$commit" || { echo "{\"case\":\"$cid\",\"label\":\"$label\",\"commit\":\"$commit\",\"result\":\"CHECKOUT_FAIL\"}" >> "$RESULT_FILE"; return 1; }
  out=$(cd "$repo" && timeout 500 hvigorw --mode module -p product=default -p buildMode=debug assembleHap --no-daemon 2>&1)
  if echo "$out" | grep -q "BUILD SUCCESSFUL"; then status=PASS; else status=FAIL; fi
  echo "{\"case\":\"$cid\",\"label\":\"$label\",\"commit\":\"$commit\",\"result\":\"$status\"}" >> "$RESULT_FILE"
  echo "[$cid $label @$commit] $status"
  [ "$status" = PASS ]
}

overall=0
for cid in "${ids[@]}"; do
  j="$ROOT/cases/$cid/case.json"
  [ -f "$j" ] || continue
  host=$(python3 -c "import json;print(json.load(open('$j'))['host_app']['local_path'].split('/')[-1])")
  u=$(python3 -c "import json;print(json.load(open('$j'))['unfixed_commit'])")
  f=$(python3 -c "import json;print(json.load(open('$j'))['fixed_commit'])")
  build_commit "$host" "$u" "$cid" unfixed || overall=1
  build_commit "$host" "$f" "$cid" fixed || overall=1
done
echo "----"
echo "overall_exit=$overall (0 = all PASS)"
exit $overall
