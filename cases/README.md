# Case structure

All 30 cases share one uniform layout. A case is reproducible when every element
below is present and consistent — `tools/verify_case_structure.py` checks it
mechanically.

```
cases/<id>/
  case.json                      uniform schema (keys listed below)
  fix.patch                      unfixed -> fixed diff
  testcase/
    <Perf|Mem>Load_<scene>_<NNNN>.py     HapRay test case (hapray.core.perf_testcase.PerfTestCase)
    <Perf|Mem>Load_<scene>_<NNNN>.json   HapRay testcase descriptor
cases/collection.yaml            shared dynamic-collection spec (mirrors HapRay)
```

## Reproducibility criteria

1. **Test cases consistent with ArkAnalyzer-HapRay** — `testcase/` holds a
   `PerfTestCase` subclass plus the `<class>.json` descriptor in the exact
   format `perf_testing/hapray/testcases/` uses (`driver.type: DeviceTest`,
   `environment: [{type: device, label: phone}]`). Copy both files into
   `perf_testing/hapray/testcases/<bundle>/` and select with
   `--run_testcases <name>`.
2. **Dynamic data collection matching HapRay** — `case.json#collection` points at
   `cases/collection.yaml`, which mirrors HapRay's `hiprofiler_cmd` session:
   ftrace plugin (24 hitrace categories + sched/task/power ftrace events),
   hiperf plugin (`-f 1000 -e raw-instruction-retired --call-stack dwarf
   --clockid boottime --kernel-callchain -m 1024`), nativehook plugin for
   `MemLoad` cases, and the periodic smaps/ui/thermal collectors. Outputs are the
   HapRay filenames (`trace.htrace`, `perf.data`, `pids.json`, `memory/`).
3. **Unfixed significantly worse than fixed on CPU/memory** —
   `case.json#test_oracle` declares exactly one CPU or memory metric:
   `hiperf_instructions` (PerfLoad cases), `app_pss_bytes` or
   `nativehook_retained_bytes` (MemLoad cases), with
   `unfixed >= 1.2 * fixed`. `fixed_commit` is immutable; the declared metric is
   the release criterion, the mechanism counter in `mechanism_oracle` is
   corroborating evidence.

## case.json keys

| key | meaning |
| --- | --- |
| `id`, `category`, `bug_description`, `perf_scenarios` | case identity |
| `host_app` | repo, bundle, `local_path`, `base_branch`, `base_commit` |
| `android_source_case`, `android_mechanism` | Android-benchmark provenance |
| `unfixed_commit`, `fixed_commit`, `fix_summary` | the pair of builds |
| `build` | last recorded `hvigorw assembleHap` result per variant |
| `testcase` | HapRay testcase: class name, files, install dir, module, ability, trigger |
| `collection` | `config` ref + `modes` (`htrace`,`hiperf`,[+`memory`]), `step_duration_s`, `rounds` |
| `test_oracle` | CPU/memory metric + comparison + evidence + mechanism_oracle |
| `reproduction` | ordered steps: seed (if any), measured step, comparison |

`PerfLoad_*` drives the UI/`--ps bench` workload while HapRay collects htrace +
hiperf; `MemLoad_*` additionally enables the nativehook plugin for the
resource-retention cases.
