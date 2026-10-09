#!/usr/bin/env bash
# Select the HarmonyOS command-line toolchain for a host.
#
# 5.1.0 applies strict ArkTS rules (arkts-no-any-unknown, arkts-no-implicit-return-types,
# arkts-no-spread) that pre-5.1 application source violates. interviewapp declares
# compatibleSdkVersion 5.0.0(12) and fails with 38 such errors under 5.1.0 while building
# unmodified under 5.0.5, so the version is chosen per host rather than globally.
#
# Usage: source device-tests/toolchain.sh [5.0.5|5.1.0]   (default 5.1.0)
TC_VERSION="${1:-5.1.0}"
case "$TC_VERSION" in
  5.0.5) TC_ROOT=/home/research/OhmBenchmark-toolchain-5.0.5 ;;
  *)     TC_ROOT=/home/research/OhmBenchmark-toolchain/command-line-tools ;;
esac
if [ ! -d "$TC_ROOT" ]; then
  echo "toolchain $TC_VERSION not found at $TC_ROOT" >&2
  return 1 2>/dev/null || exit 1
fi
export OHM_TC_ROOT="$TC_ROOT"
export DEVECO_SDK_HOME="$TC_ROOT/sdk"
export PATH="$HOME/.local/bin:$TC_ROOT/bin:$PATH"
