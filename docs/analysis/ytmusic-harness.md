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

## Driving the real render path

The first version of the bench parsed fixture rows itself, so the instrumented call sites in
`History.ets` were never exercised and the counter would have read 0 for both variants - the
same trap that produced "unfixed 1000, fixed 0" on the flush case.

The bench now drives the page under test:

1. `prepare()` seeds AppStorage key `history` with 200 distinct entries, which is where the
   page reads its rows from (`@StorageLink('history')`);
2. the measured action routes to `pages/History` and waits, so the page's own `ForEach` builds
   the rows;
3. the counter is read **after** the render, and the instrumented helper keeps a running total
   rather than a per-measurement one, because `ForEach` runs on the UI thread during the page
   transition - by the time the async action resumes, the parses have already happened.

The running total is read by the bench from the instrumented page rather than from `OhmProbe`,
because `History.ets` is imported by the bench and having the probe import it back would be a
cycle.

## Status

- harness: **done and building**
- instrumentation: **done for the json_parse case (4 sites, running total)**
- render path: **driven**
- measurement: **not yet run on device**
