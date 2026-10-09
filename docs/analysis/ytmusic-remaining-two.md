# ytmusic: the two remaining cases, and why each is harder than it looks

`ytmusic_history_json_parse_per_row` is measured (600 vs 200 parses, see
`ytmusic-harness.md`). The other two ytmusic cases share the same harness but need a different
kind of driver, and the difference matters.

## ytmusic_search_no_debounce

Declared metric `search_requests_per_query`. Oracle: "unfixed: ~11 requests per typed query
(one per keystroke + submit); fixed: 1-2 requests."

The fix moves the `axios.get('https://yt.c12k.dev/search', ...)` call out of the
`TextInput.onChange` handler and behind a 300 ms debounce timer.

**Why the history approach does not transfer.** The history case worked because the bench could
seed `AppStorage` and route to the page, and the page then did its parsing on render. Here the
counted work happens in `onChange`, which fires only from real typing. The bench cannot type
into a `TextInput`, and the component's private timer is not reachable from outside it.

**Two viable approaches, in order of preference:**

1. **Drive the input event.** `TextInput` supports programmatic text plus a controller; if the
   page's `onChange` can be reached through a component reference or by exposing a test hook
   behind the bench, the bench can fire N changes in quick succession and then wait past the
   debounce window. This mirrors the flush case exactly: unfixed fires one request per change,
   fixed fires one after the timer settles - and the fixed count must be read *after* the
   debounce window, or it reads 0. That trap already cost a round on the flush case.
2. **Count at the HTTP boundary** rather than in the page, by instrumenting the axios call
   site and driving the page's public behaviour. Counting at the boundary measures the same
   thing the oracle describes and is robust to how the input is produced.

**Network dependency.** `https://yt.c12k.dev/search` is an external host. The unfixed variant
issues a request per keystroke, so a burst of 11 requests depends on the network being up and
on the endpoint answering; failures would be counted as requests only if the counter sits
before the call. The counter must therefore be incremented **before** the request is issued, so
the metric measures attempted requests, which is what the oracle's "requests per query"
describes.

## ytmusic_current_playing_timeupdate

Declared metric `player_page_updates_per_minute`. Oracle: "unfixed ~600 updates/minute vs fixed
~60/minute."

The fix makes the player update its progress state only when the displayed second changes,
instead of on every `timeUpdate` callback.

**This is the closest of the three to the history case** and should be attempted first: the
bench can seed the player state, route to `pages/CurrentPlaying`, and the page's own render path
does the counted work. The counter goes on the state update itself, and the measured window
must be long enough for at least a few seconds of playback ticks.

**Caveat worth stating up front:** the oracle's figures are per *minute* (600 vs 60), which
needs a 60-second measurement window per run to reproduce directly. A shorter window measures
the rate and scales it, which is defensible but should be labelled as a rate, not a count over
a minute - otherwise the reported number silently differs from what the oracle declares.

## What is already in place

- the harness (`OhmProbe.ets`, `Diag.ets`, `YtMusicBench.ets`) builds, installs and runs;
- the append-only `ohm-diag.json` checkpoint pattern is proven to work where the status file
  overwrote diagnostics;
- `SUMMARY_SOURCE=diag:<key>` reports a metric from the archived log, and the coverage report
  counts it;
- the instrumenter already rewrites `JSON.parse` sites in all three pages, and its structure
  generalises to the search and player call sites.

## Reproduce what exists

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:parseTotal bash device-tests/run_declared_metric.sh \
  ytmusic_history_json_parse_per_row ytmusic 627611f 157104d \
  self-installing:tools/instrument_ytmusic.py 3
```
