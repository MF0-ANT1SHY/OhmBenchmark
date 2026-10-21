# Ordinary search payload acceptance

The app's original per-keystroke search and 300 ms debounce variants are retained. Both candidate builds change only the search origin to the same ordinary service at `http://127.0.0.1:18493/search`. No counters, evaluator routes, readiness fields, or profiling hooks are added to the app.

## Reproduction conditions

The device is attached to HKRC through Tailscale. Run `tools/ytsearch_workstation_lease.py` with `ytsearch_data_service.py` and `workstation_process.py` beside it on the workstation. Its foreground lease is bounded to 7,200 seconds. The collector establishes HDC reverse forwarding within its native capture connection. The service contains 20 complete ordinary song records, a shared cover, and conventional case-insensitive substring search. There is no artificial network delay and no padded response fields.

`tools/capture_ytsearch_payload.py` installs each signed variant, opens its ordinary search page, types ten keys spelling `electronic`, and submits. Native layouts prove empty initial input, complete final input, and expected result titles, creators, and durations. Completed server response bodies are hashed and byte-counted outside the app. Whole-catalogue queries, source hashes, and service process identity are checked before and after each action. The private request log is not a service endpoint.

## Metric and limits

The predeclared primary metric is successful search JSON response-body bytes written and flushed by this isolated backend during the native input action. It excludes HTTP headers, image bodies, and unrelated home-page traffic. It is not a claim about radio bytes or CPU speedup.

The unfixed variant must complete all ten prefix searches plus submit. The fixed variant must complete one or two full-query searches and no prefix searches. Each of three paired ratios and their median must reach 5.0. Native scheduler data is independently checked and is diagnostic only. Preflight observations are not formal performance acceptance. Failures, partial writes, altered bodies, and requests outside the action window are rejected.

`tools/accept_ytsearch_payload.py` revalidates original native layouts, request receipts, signed identities, fixture checks, and trace data. The original CPU-pending contract is archived only when a complete replacement contract is accepted.

Agent exports contain only the audited unfixed HAP, app-only native scheduling profile, normal UI workload, reproduction script, and symptom. Private service receipts, oracle fields, comparison ratios, and fixed packages stay outside the diagnosis workspace.
