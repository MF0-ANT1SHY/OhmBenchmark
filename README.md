# OhmBenchmark — HarmonyOS Performance-Bug Cases

30 reproducible performance-bug cases on HarmonyOS / OpenHarmony NEXT, migrated
from an Android performance-bug benchmark. Each case is a pair of builds —
unfixed (buggy) and fixed — of a real open-source HarmonyOS app, plus trigger
steps and a device-test oracle.

## Layout

- `cases/<id>/case.json` — host app, unfixed/fixed commits, trigger steps, oracle
- `cases/<id>/fix.patch` — the unfixed→fixed diff
- `cases/<id>/testcase/` — HapRay-format testcase and collection spec
- `cases/collection.yaml` — shared hiprofiler/hiperf capture config
- `cases/README.md` — case structure and reproducibility criteria
- `harness/` — reusable ArkTS instrument probes for measuring new cases

## Adding a new case

1. Pick a real performance bug (or a realistic refactor of a real code path) in
   a public HarmonyOS app; no sleeps, dummy loops or artificial delays.
2. Create `cases/<id>/` following `cases/README.md`: `case.json`, `fix.patch`,
   `testcase/`, with a measurable oracle (unfixed >= 1.2x fixed, >= 3 rounds).
3. For device measurement, derive a counter from `harness/OhmProbe.ets` (see
   existing `Ohm*Count.ets` probes for patterns), inject it into both builds,
   and record the measured evidence in `case.json`.

## Removed content

The measurement pipeline scripts, host reconstruction patches, signing docs and
raw-data inventory were slimmed away; find them in git history at tag
`full-pipeline-2026-10-10`. Raw device data stays outside the repo
(`/home/research/OhmBenchmark-data/`, see DATA.md at that tag).
