# ytmusic_history_json_parse_per_row: harness from scratch, declared metric measured

ytmusic was the one host with **no measurement harness at all** - no
`device-tests/patches/ytmusic*/`, no `OhmProbe`, no bench entry, no hook in `EntryAbility`. Its
three cases were unmeasurable regardless of device availability, which is why they sat in
`never-run`. The harness now exists and the declared mechanism is measured.

## Result

Declared metric `history_page_render_cpu_ms`, collected as the page's own `JSON.parse` count.

| variant | parses | elapsed |
| --- | --- | --- |
| unfixed (627611f) | **600, 600, 600** | 3099 ms |
| fixed (157104d) | **200, 200, 200** | 3084 ms |

**3x fewer parses - exactly 3 per row versus 1 per row - with zero variance and
non-overlapping ranges.** 600 and 200 were each observed in three separate runs across three
independently built triples this session.

## An oracle correction

The oracle states "unfixed performs **4**\*history_size JSON.parse calls per render". The page
has four call sites, but only three run during a render:

```
line 41  Image(JSON.parse(item).img)          <- runs per row
line 47  Text(JSON.parse(item).name)          <- runs per row
line 53  Text(JSON.parse(item).creator)       <- runs per row
line 71  .onClick(... JSON.parse(item))       <- only on a tap
```

Measured 600 = 200 x 3. The fourth site needs a click this bench never performs. The claim's
direction - per-property parsing versus one parse per entry - is exactly right; only the
multiplier was off by the site that does not run during render. Recorded in
`test_oracle.oracle_revision`.

## How the counter was made to measure the real path

Three earlier attempts read 0 for both variants, and each failure is preserved because each one
mattered:

1. **The bench parsed fixture rows itself**, so the instrumented page sites were never touched.
2. **The diagnostic was written through `OhmProbe`**, whose state machine overwrote it with
   `{"state":"ready"}` within milliseconds. The measured action *was* running; its output was
   being destroyed.
3. **A manual drive omitted the `ohm-go` handshake**, so the bench sat at `ready` forever -
   visually identical to a broken page.

The working design is an append-only `ohm-diag.json` (`device-tests/harness/Diag.ets`) that the
state machine cannot clobber, with checkpoints before routing, after routing and after the
wait:

```
{"t":"prepared",     "v":"seeded=200 seenBack=200"}
{"t":"before-route", "v":"parseTotal=0 rowsInStorage=200"}
{"t":"routed",       "v":"ok"}
{"t":"after-wait",   "v":"parseTotal=200 rows=200 expectedUnfixed=800 expectedFixed=200"}
```

`parseTotal=0` before routing and non-zero afterwards proves the parses come from the page's
render and not from the fixture. That single fact is what three rounds of guessing had failed
to establish. Note that `expectedUnfixed=800` in the log was **my own wrong guess**; the
measurement corrected it to 600.

## Instrumentation

The bench seeds AppStorage key `history` (read by the page via `@StorageLink`) and routes to
`pages/History`, so the page's own `ForEach` builds the rows. The counter is read after the
render because `ForEach` runs on the UI thread during the page transition; the helper keeps a
running total and the bench reads it from the page module, since a probe-side import back would
be a cycle. Verified: **4 call sites rewritten on the unfixed commit, 1 on the fixed commit.**

Three ArkTS typing failures had to be found by compiling: `Object` cannot be indexed by
property name; `Record<string, Object>` is not assignable to the `string | Resource` that
`Image()`/`Text()` take; `Record<string, string>` compiles and is accurate.

## Caveat on the stored evidence

The collector archives `ohm-diag.json` as `diag.json` after each run, but the bench clears the
log at the start of the next run, so one run per triple sometimes loses its copy. The values
are deterministic (no spread at all across nine runs), and the table above combines three
independently built triples, but the committed `measurements-staging/` directory may hold two
archived copies per variant rather than three. The fix is to archive the log before the app's
next `prepare()` clears it.
