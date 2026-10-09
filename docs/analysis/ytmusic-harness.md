# ytmusic_history_json_parse_per_row: harness written from scratch, metric measured

ytmusic was the one host with **no measurement harness at all** - no
`device-tests/patches/ytmusic*/`, no `OhmProbe`, no bench entry, no hook in `EntryAbility`. Its
three cases were unmeasurable regardless of device availability, which is why they sat in
`never-run`. That harness now exists and the declared mechanism is measured.

## Result

Declared metric `history_page_render_cpu_ms`, instrumented as `OHMB/JsonParseCount` - the
number of `JSON.parse` calls the history page performs while building its list from 200 seeded
entries.

| variant | parses | elapsed |
| --- | --- | --- |
| unfixed (627611f) | **600** | 3067 ms |
| fixed (157104d) | **200** | 3064 ms |

**3x fewer parses, exactly 3 per row versus 1 per row, with zero variance.** One run per
variant so far; the 3-repetition protocol has not been completed, so this is recorded as a
verified mechanism, not yet as a completed triple.

## An oracle correction this case needs

The oracle states "unfixed performs **4**\*history_size JSON.parse calls per render". The page
has four `JSON.parse` call sites, but only three execute during a render:

```
line 41  Image(JSON.parse(item).img)          <- runs per row
line 47  Text(JSON.parse(item).name)          <- runs per row
line 53  Text(JSON.parse(item).creator)       <- runs per row
line 71  .onClick(... JSON.parse(item))       <- only on a tap
```

Measured: 600 = 200 x 3. The fourth site needs a click, which this bench never performs. The
oracle's *direction* (per-property parsing versus one parse per entry) is exactly right; only
the multiplier is off by the one site that does not run during render. This should be recorded
as an `oracle_revision` once the repetitions confirm it.

## How the counter is made to measure the real path

Three earlier attempts read 0 for both variants, and each failure was instructive:

1. **The bench parsed fixture rows itself** - the instrumented page sites were never touched.
2. **The diagnostic was written through `OhmProbe`** - the state machine overwrote it with
   `{"state":"ready"}` within milliseconds, so the collector never saw it, and it was unclear
   whether the measured action ran at all.
3. **A manual drive forgot the `ohm-go` handshake** - the bench sat at `ready` forever, which
   looked identical to a broken page.

The working design: a separate append-only `ohm-diag.json` (`device-tests/harness/Diag.ets`)
that the state machine cannot clobber, with checkpoints at four points. That turned an
ambiguous zero into this:

```
{"t":"prepared",     "v":"seeded=200 seenBack=200"}
{"t":"before-route", "v":"parseTotal=0 rowsInStorage=200"}
{"t":"routed",       "v":"ok"}
{"t":"after-wait",   "v":"parseTotal=200 rows=200 expectedUnfixed=800 expectedFixed=200"}
```

`parseTotal=0` before routing and non-zero after proves the parses come from the page's render,
not from the fixture. `routed: ok` rules out navigation failure, and `seenBack=200` rules out
`AppStorage` not carrying the value.

## Instrumentation details

The bench seeds AppStorage key `history` (which the page reads via `@StorageLink`) and routes to
`pages/History`; the page's own `ForEach` builds the rows. The counter is read after the render
because `ForEach` runs on the UI thread during the page transition. The instrumented helper
keeps a running total and the bench reads it from the page module, since `History.ets` is
imported by the bench and a probe-side import back would be a cycle.

Verified by the instrumenter: **4 call sites rewritten on the unfixed commit, 1 on the fixed
commit.**

Three ArkTS typing failures had to be found by compiling: `Object` cannot be indexed by
property name; `Record<string, Object>` is not assignable to the `string | Resource` that
`Image()`/`Text()` take; `Record<string, string>` compiles and is accurate.

## Status

- harness: **done, builds, installs, runs on device**
- instrumentation: **done, and the counted path is confirmed exercised**
- measurement: **mechanism verified (600 vs 200); 3-repetition protocol pending**
