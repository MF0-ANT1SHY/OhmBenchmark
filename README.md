# OhmBenchmark — business-only HarmonyOS performance cases

30 cases across nine apps, each with unfixed/fixed business source trees, a repair
diff and an external UI workload. **No injected benchmark code is compiled into
the apps.** Renaming probes or hiding their outputs does not satisfy this rule.

## Layout

- `cases/<id>/case.json` — evaluator-only identity, source refs, oracle and gate status
- `cases/<id>/fix.patch` — unfixed→fixed business diff
- `cases/<id>/testcase/` — HapRay testcase, external workload plan and shared UI driver
- `cases/collection.yaml` — system-level profiling configuration
- `hosts_patches/` — upstream reconstruction and explicit production adaptations
- `tools/` — reconstruction, build, bytecode audit, signing and external device tools
- `validation/clean-builds.json` — artifact hashes and separate runtime gates

## Rebuild

```bash
python3 tools/reconstruct_clean_hosts.py
python3 tools/build_clean_cases.py
python3 tools/sign_clean_cases.py
python3 tools/smoke_clean_cases.py
```

`toolchain/command-line-tools` must point to the SDK toolchain (5.1.0.840 used).
Signing/device tools default to the existing `cityuPC` SSH alias and Ubuntu-24.04
WSL workstation. Signing keys stay there; app bundle names are not rewritten.
See `cases/README.md` for external preparation and performance acceptance.

## Blind-evaluation boundary

Give the diagnosis agent only the **clean unfixed HAP**, symptom description,
neutral UI reproduction driver and system-generated profiles. Exclude case
metadata, repair diffs, fixed packages, fixture/oracle inventories and evaluator
receipts. No app-side counters, custom traces, diagnostics, bench entrypoints,
gates, simulations or instrumentation wrappers are allowed in clean HAPs.

Export to a fresh directory outside the evaluator checkout:

```bash
python3 tools/export_agent_data.py browser_eager_history_load /tmp/diagnosis-app \
  --symptom '启动浏览器时响应较慢'
```

The default binary-only export contains the captured unfixed package, neutral UI
workload/standalone `reproduce.py`, symptom and app-scoped system report. Source
is excluded; use `--include-source` only for separately identified source-enabled
diagnosis (the archive excludes git history). Run
`python3 reproduce.py` in a prepared diagnosis environment with `hdc` available. The
device JSON reporter does not reliably honor `--pids`; this exporter explicitly
filters processes, threads and unreferenced symbols/libraries and recomputes
totals. Do not give agents the private all-process reports or capture receipts.

## Validation status

Build/audit, install/launch, real-workload and performance gates are separate.
Migration is not complete until all 30 workloads and declared CPU/memory oracles
are verified on the clean pairs. Historical instrumented evidence is archived
for provenance and **does not validate these rebuilt cases**.

Retired probes and measurement patches remain only in git history at
`full-pipeline-2026-10-10`; do not apply them to clean builds.
