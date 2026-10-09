# wanharmony_web_progress_log_storm: declared metric measured

## Result

Declared metric `log_calls_per_pageload`, collected as the number of progress events the page's
guard admits over the sequence a load produces (`0..100`).

| variant | log calls | elapsed |
| --- | --- | --- |
| unfixed (d1618b9) | **101, 101, 101** | n/a |
| fixed (cb8a8ea) | **5, 5, 5** | n/a |

**95% fewer log calls, zero variance, non-overlapping.** The oracle predicted "dozens per page"
versus "<= 5 per page", and 101 versus 5 is exactly that: every progress value logs unguarded,
while the milestone test admits `0, 25, 50, 75, 100`.

## What is measured, stated precisely

The bench drives `ohmProgressLogWouldLog` - the variant's own guard, whose body is written from
the source under test - over the progress sequence. It does **not** observe a WebView's event
cadence, because that is impossible here: `onProgressChange` is a `Web` component event that
cannot be synthesised, and a real page load would need a reachable URL, which is the fixture
problem already documented as blocking in this environment.

This is weaker evidence than counting work the app really performs, and the distinction matters:
what is established is that **the two guards differ by 101 versus 5 on an identical input
sequence**, which is the mechanism the case is about. It is not evidence about how many progress
events a real page emits.

The handler in `WebPage.ets` is instrumented too, so a genuine in-app load would also be counted.

## Two instrumenter bugs found and fixed

1. **A duplicate `log` import** - the block inserted for the bench repeated the import line it was
   anchored on, so the build failed with "Duplicate identifier 'log'" at two consecutive lines.
2. **The driver required a file named `OhmProbe.ets`.** This harness signals from
   `OhmLogCount.ets`, so a correctly built harness was rejected as "no OhmProbe.ets anywhere in
   the host". The check now looks for the *ability* to write `ohm-status.json`, which is what the
   collector actually depends on, and so works regardless of what a harness names its file.

## And the handshake

The first successful run wrote `done` before the collector observed `ready`, so every run timed
out even though the value was already visible in the timeout message (`result: 5`). The bench now
follows the same protocol as every other harness - write `ready`, wait for the collector to touch
`ohm-go`, then measure - which is what makes the collected window the collector's rather than a
race against it.

## Caveat on the stored evidence

Two archived runs per variant rather than three: the collector archives `ohm-diag.json` after each
run and the bench clears it at the start of the next, so one per triple can be lost. The values
are deterministic across six runs, but the committed evidence holds two copies.
