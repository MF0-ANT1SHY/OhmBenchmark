# wanharmony_web_progress_log_storm: instrumented, driver still missing

## The case

Declared metric `log_calls_per_pageload`: "Count of hilog invocations from the app during page
load (progress-event logs)". The unfixed page logs on **every** progress event; the fixed page
guards with `newProgress === 100 || newProgress % 25 === 0`, so at most five per page.

## What is done and verified

`tools/instrument_progress_log.py`:

- counts at the single `log()` entry point in `LogUtils.ets`, which every progress log passes
  through - so the count is robust to which call site logs;
- instruments the `onProgressChange` handler in `WebPage.ets`, keeping each variant's own body
  (unconditional for unfixed, the milestone guard for fixed);
- writes `OhmLogCount.ets` with `ohmProgressLogBump()` (an imported binding cannot be assigned
  to, which the compiler enforced) and `ohmProgressLogWouldLog(progress)`, whose body is written
  per variant.

**Both variants build and the guard is correct in each**, which is the part that matters:

| variant | guard body in the counter module | build |
| --- | --- | --- |
| unfixed `d1618b9` | `return true;` | BUILD SUCCESSFUL |
| fixed `cb8a8ea` | `return progress === 100 || progress % 25 === 0;` | BUILD SUCCESSFUL |

## Why the guard is made callable

The handler cannot be triggered by the bench. `onProgressChange` is a `Web` component event that
cannot be synthesised, and a real page load would need a reachable URL - the fixture problem
already documented as blocking in this environment. Instrumenting the handler alone therefore
counts nothing.

The guard is the *only* difference between the variants, so it is exposed as a pure function the
bench can drive over the progress sequence a page load produces (`0..100`). That yields 101 for
an unguarded page and 5 for a milestone-guarded one - the declared metric, with the guard
exercised directly rather than the WebView's event cadence observed. Any write-up must say that
plainly.

## What is missing

1. **The bench does not call the guard yet.** The counter and guard exist and build, but nothing
   drives `ohmProgressLogWouldLog` over the sequence and reports the total. That is the remaining
   piece, and it is small: a bench entry that loops `0..100`, counts the `true` results, and
   emits the total through the diag channel the other cases use.
2. **The wanharmony harness patch only partly applies.** Applying
   `device-tests/patches/wanharmony_history_log_materialization/unfixed.patch` reports
   `error: entry/src/main/ets/pages/HistoryPage.ets: patch does not apply` for both commits, and
   the build still succeeds because `WebPage.ets` and `OhmProbe.ets` are what this case needs.
   That is fine here but means **no run has been installed to the device from this tree**, so
   nothing about the harness has been verified end to end for this case - unlike the ytmusic and
   interviewapp harnesses, which reached `state=ready`.

## Exact next steps

```bash
cd /home/research/OhmBenchmark-main
source device-tests/toolchain.sh 5.1.0
git -C hosts/wanharmony checkout --force d1618b9 && git -C hosts/wanharmony clean -fd
git -C hosts/wanharmony apply device-tests/patches/wanharmony_history_log_materialization/unfixed.patch
python3 tools/instrument_progress_log.py
# then: add the bench entry that drives ohmProgressLogWouldLog over 0..100,
# build, sign, install, and run the 3-repetition protocol
```

Expected once driven: unfixed **101** log calls, fixed **5** - the oracle's "dozens per page"
versus "<= 5 per page".

## Reproduce the instrumenter alone

```bash
python3 tools/instrument_progress_log.py     # idempotent
```
