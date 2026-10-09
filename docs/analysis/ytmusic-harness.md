# ytmusic: the measurement harness, written from scratch

ytmusic was the one host with **no measurement harness at all** - no
`device-tests/patches/ytmusic*/`, no `OhmProbe`, no bench entry, no hook in `EntryAbility`.
Its three cases were therefore unmeasurable regardless of device availability, which is why
they sat in `never-run`.

## What now exists

| file | role |
| --- | --- |
| `device-tests/harness/OhmProbe.ets` | probe: writes the `ohm-status.json` state machine (`preparing` -> `ready` -> `done`/`error`), waits for the host to touch `ohm-go` so profiling starts before the measured region, emits `OHMB/<case>` trace markers, and carries per-case counters |
| `device-tests/harness/YtMusicBench.ets` | bench entry for the three ytmusic cases |
| `tools/instrument_ytmusic.py` | installs both, hooks `EntryAbility.onNewWant` on a `bench` want parameter, and instruments the case under test |

Build verified: **BUILD SUCCESSFUL**, producing
`hosts/ytmusic/entry/build/default/outputs/default/entry-default-unsigned.hap`.

## Instrumentation for ytmusic_history_json_parse_per_row

The unfixed history page parses each entry's JSON **per property access** inside `ForEach`:

```
ForEach(..., (item: string) => {
  Image(JSON.parse(item).img)
  Text(JSON.parse(item).name)
  Text(JSON.parse(item).creator)
  ...
})
```

The fixed page parses once per entry outside the row builder:

```
ForEach(Array.from(this.history).reverse().map((item) => JSON.parse(item)), ...)
```

`tools/instrument_ytmusic.py` routes every `JSON.parse` call site in `History.ets` through a
counting `ohmParse` helper - **4 call sites found and rewritten** - so the count is exact
rather than inferred from timing.

## Two ArkTS typing problems, both real

The helper's return type had to be found by compiling, twice:

1. `Object` failed: "Property 'creator' does not exist on type 'Object'" - the page indexes
   into the parsed value by name.
2. `Record<string, Object>` failed: "Argument of type 'Object' is not assignable to parameter
   of type 'string | Resource'" - the values feed `Image()` and `Text()`.
3. `Record<string, string>` compiles, and is accurate: the payload's `img`, `name` and
   `creator` are all strings.

## Known limitation, not yet measured

The bench entry currently parses fixture rows itself instead of driving the history page's
own render path, so the instrumented call sites in `History.ets` are **not yet exercised** and
the counter would read 0 for both variants. Before this case can be measured, the bench must
make the history page build its list - either by seeding real history entries in `prepare()`
and navigating to the page, or by extracting the page's row-building into something the bench
can call directly. This is written down rather than papered over: the harness is a
prerequisite, not the measurement.

## Status

- harness: **done and building**
- instrumentation: **done for the json_parse case (4 sites)**
- measurement: **not yet run**
