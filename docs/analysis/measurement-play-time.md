# cloudmusic_play_time_high_frequency_update: declared metric measured

## Result

Declared metric `player_page_rerenders_per_minute`, collected as the number of PLAY_TIME writes
the page's guard admits over the 600 ticks one minute of playback produces.

| variant | state writes | oracle expectation |
| --- | --- | --- |
| unfixed (2aa4715) | **600, 600, 600** | ~600/minute (10/s) |
| fixed (d755085) | **60, 60, 60** | ~60/minute (1/s) |

**90% fewer state writes, zero variance, non-overlapping**, and both figures land exactly on the
oracle's stated rates.

## What is measured, stated precisely

The bench drives `ohmPlayWouldWrite` - the variant's own guard, written from the source under test
- over the tick sequence, committing each admitted second the way the source assigns
`lastReportedSecond`. It does **not** observe a real player: `timeUpdate` cannot be synthesised and
a real minute of playback would dominate a run. What is established is that the two guards differ
600 versus 60 on identical input, which is the mechanism the case declares.

The `AppStorage.setOrCreate(PLAY_TIME, ...)` write site is instrumented too, so genuine playback
would also be counted.

## The install blocker, and how it was resolved

The bundle would not install:

```
code:9568289 install failed due to grant request permissions failed.
PermissionName: ohos.permission.SYSTEM_FLOAT_WINDOW
```

`SYSTEM_FLOAT_WINDOW` is system-grant only, so a locally signed build is rejected. It gates
`WindowUtils`' float-window creation, which is unrelated to PLAY_TIME writes, so the instrumenter
removes the request - **a minimal, documented deviation applied identically to both variants**, so
the comparison stays fair. The install then succeeded, which is the evidence the removal reached
the artifact.

Two earlier attempts produced this same error while the removal had in fact worked, because the
build failed before packaging and `hdc install` installed the **stale HAP from the previous
build**. Checking the packaged `module.json` is what distinguished the two.

## Why the counter was not being compiled

The counter's import failed with "Cannot find module '../../OhmPlayTimeCount'" although the file
existed and the path was provably correct - the host's own `'../../constants/StorageConstants'`
import resolves from the same directory, which fixes the depth at two levels.

An A/B test settled it: the **same file** at `common/utils/OhmPlayTimeCount.ets` does not resolve,
while at `common/constants/OhmPlayTimeCount.ets` - imported as `'../../constants/OhmPlayTimeCount'`,
the exact shape the host already uses - the build succeeds. The counter therefore lives in
`common/constants/`.

Ruled out on the way: a stale ArkTS build cache (cleared, still failed), wrong relative depth
(verified against the host's own imports), encoding problems, and `.gitignore` filters.

## Reproduce

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:writes bash device-tests/run_declared_metric.sh \
  cloudmusic_play_time_high_frequency_update cloudmusic 2aa4715 d755085 \
  self-installing:tools/instrument_play_time.py 3
```
