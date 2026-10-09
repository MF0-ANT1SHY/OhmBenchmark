# ytmusic: the measurement harness, written from scratch

ytmusic was the one host with **no measurement harness at all** - no
`device-tests/patches/ytmusic*/`, no `OhmProbe`, no bench entry, no hook in `EntryAbility`. Its
three cases were therefore unmeasurable regardless of device availability, which is why they
sat in `never-run`.

## What now exists

| file | role |
| --- | --- |
| `device-tests/harness/OhmProbe.ets` | probe: `ohm-status.json` state machine (`preparing` -> `ready` -> `done`/`error`), `ohm-go` handshake so profiling starts before the measured region, `OHMB/<case>` trace markers, per-case counters |
| `device-tests/harness/YtMusicBench.ets` | bench entry for the three ytmusic cases |
| `tools/instrument_ytmusic.py` | installs both, hooks `EntryAbility.onNewWant` on a `bench` want parameter, and instruments the case under test |

**Verified on device**: the harness builds, signs, installs, reaches `state=done` and collects
six runs (three per variant) in ~3s each. Before this round the host could not be measured at
all.

## Instrumentation for ytmusic_history_json_parse_per_row

The unfixed history page parses each entry's JSON **per property access** inside `ForEach`:

```
Image(ohmParse(item).img)
Text(ohmParse(item).name)
Text(ohmParse(item).creator)
```

The fixed page parses once per entry outside the row builder. All **4** `JSON.parse` call sites
in `History.ets` are routed through a counting `ohmParse` helper, so the count is exact rather
than inferred from timing. The helper keeps a running total, and the bench reads it after the
render, because `ForEach` runs on the UI thread during the page transition.

## Three ArkTS typing problems, all real

The helper's return type had to be found by compiling:

1. `Object` - rejected: "Property 'creator' does not exist on type 'Object'".
2. `Record<string, Object>` - rejected: "Argument of type 'Object' is not assignable to
   parameter of type 'string | Resource'" (the values feed `Image()` and `Text()`).
3. `Record<string, string>` - compiles, and is accurate for this payload.

## The open problem

**The counter reads 0 for both variants**, over three runs each. The bench returns
`result: 200` consistently, so the fixture is being seeded and read, but the parses the oracle
counts are not happening on this path.

Most likely causes, in order:

1. **The page is not actually being built.** `router.pushUrl({url: 'pages/History'})` may be
   failing silently, or the page may be built asynchronously later than the 2500ms the bench
   waits, or `@StorageLink('history')` may not pick up a value set via `AppStorage.setOrCreate`
   from a non-UI context.
2. **`this.history.size > 0` is false at build time**, so the `ForEach` branch is skipped
   entirely and no parsing occurs - which would produce exactly the observed 200/0 pattern,
   since the fixture is read but never rendered.
3. **The instrumented module is not the one that ships.** The bench imports `ohmParseTotal`
   from `../pages/History`; if the bundler resolves a different copy than the page uses, the
   counter would stay 0.

The cheapest next check is to make the page report its own state: have `prepare()` write the
seeded row count and the bench write `history.size` observed from the page, so the run output
distinguishes "not rendered" from "rendered but not counted".

This is written down rather than papered over. A counter that reads 0 on both variants is not
a null result - it is an unexercised path, the same failure mode that produced "unfixed 1000,
fixed 0" on the flush case.

## Status

- harness: **done, builds, installs, runs on device**
- instrumentation: **done (4 sites, running total, emitted after render)**
- measurement: **path not yet exercised; counter reads 0 both variants**
