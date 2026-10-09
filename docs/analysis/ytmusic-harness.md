# ytmusic: harness written from scratch; measurement path still blocked

ytmusic was the one host with **no measurement harness at all** - no
`device-tests/patches/ytmusic*/`, no `OhmProbe`, no bench entry, no hook in `EntryAbility`. Its
three cases were unmeasurable regardless of device availability, which is why they sat in
`never-run`.

## What now exists and is verified on device

| file | role |
| --- | --- |
| `device-tests/harness/OhmProbe.ets` | `ohm-status.json` state machine (`preparing` -> `ready` -> `done`/`error`), `ohm-go` handshake, `OHMB/<case>` trace markers, per-case counters |
| `device-tests/harness/YtMusicBench.ets` | bench entry for the three ytmusic cases |
| `tools/instrument_ytmusic.py` | installs both, hooks `EntryAbility.onNewWant`, instruments the case |

Builds, signs, installs, reaches `state=ready`, and has completed six collection runs in ~3s
each. The driver gained `self-installing:<tool>` (for hosts with no harness patch) and now
checks for `OhmProbe` *after* instrumentation rather than before it.

## Instrumentation for ytmusic_history_json_parse_per_row

The unfixed history page parses each entry's JSON per property access inside `ForEach`; the
fixed page parses once per entry. Verified by the instrumenter itself: **4 call sites
rewritten on the unfixed commit, 1 on the fixed commit**, which matches the fix's shape.

Three ArkTS typing failures had to be found by compiling: `Object` cannot be indexed by
property name; `Record<string, Object>` is not assignable to the `string | Resource` that
`Image()`/`Text()` take; `Record<string, string>` compiles and is accurate for this payload.

## Where the measurement is blocked

The parse counter reads **0 for both variants** while the bench returns `result: 200`
consistently. Confirmed so far:

- `pages/History` **is** a registered route (`main_pages.json`), and `router.pushUrl({url:
  'pages/History'})` is exactly how the app itself navigates there, so the route is not the
  problem;
- the bench *does* return 200, so `prepare()` runs;
- a diagnostic written during `prepare()` was **overwritten by the `ready` state within
  milliseconds**, so the polling collector never observed it, and **no diagnostic from the
  measured action ever appeared** - meaning the action most likely did not run, or ran and
  returned before its own write.

The `result: 200` needs re-examination on that basis: it equals the fixture row count, so it
may be produced without the page's `ForEach` ever building a row. An earlier report of six
completed runs said "the harness works" on the strength of `state=done`; that was too
generous, and this note corrects it.

## Cheapest next diagnostic

Write the diagnostic to a **separate file** (`ohm-diag.json`) that the `ready`/`done` writes do
not clobber, and include a counter read at three points: before routing, after routing, and
after the wait. That distinguishes "action never ran" from "routed but page did not build"
from "built but counter not shared" in a single run.

## Status

- harness: **done, builds, installs, runs on device**
- instrumentation: **done (4 sites unfixed, 1 fixed)**
- measurement: **blocked - path not exercised, counter reads 0**
