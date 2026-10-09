# Declared-metric results: the first two cases

These are the first cases whose **declared** `test_oracle.metric` is actually collected, over
the full 3-repetition protocol, with builds made from the cases' recorded commits.

Method: `device-tests/run_declared_metric.sh` (see `collecting-declared-metrics.md`).
New runs are staged under `measurements-staging/`; the original `measurements/` session is
untouched. Instrumentation is identical in both variants and changes no behaviour.

## browser_insert_date_lookup_cache

Declared metric: `rdb_statements_per_page_save` (RDB statements attributable to history
saving). Instrumented as `OHMB/StatementCount` by `tools/instrument_statement_count.py`.

| variant | statements | elapsed |
| --- | --- | --- |
| unfixed | **3000, 3000, 3000** | 7235 ms (median) |
| fixed | **1002, 1002, 1002** | 2548 ms (median) |

- median reduction **66.6%** on the declared metric, **64.8%** on elapsed
- **ranges do not overlap** (3000 > 1002, zero spread either side)
- 3000 = 1000 saves x (date_table SELECT + CREATE TABLE + history INSERT), exactly the shape
  the oracle predicts; the fixed build pays 1000 history INSERTs plus the 2 the first save
  for the date still incurs before its cache entry exists

## sheafreader_unread_counts_n_plus_1

Declared metric: `sidebar_count_queries_per_refresh` (RDB SELECTs per sidebar refresh).
Instrumented as `OHMB/QueryCount` by `tools/instrument_query_count.py`.

| variant | queries | elapsed |
| --- | --- | --- |
| unfixed | **201, 201, 201** | 3286 ms (median) |
| fixed | **2, 2, 2** | 112 ms (median) |

- median reduction **99.0%** on the declared metric, **96.6%** on elapsed
- **ranges do not overlap**
- 201 = 200 feeds + `getAllFeeds`; 2 = `getAllFeeds` + the single GROUP BY, exactly the
  declared shape ("unfixed: N queries per refresh, one per feed; fixed: 1")

## What this establishes

Both cases move from `collected-not-used` to having their declared metric genuinely
collected, with zero between-run spread and non-overlapping ranges. The instrumentation is
reproducible from the repository: commit -> measurement patch -> instrumenter -> build ->
sign -> install -> collect.

## What it does not establish

- **One device, one session.** Three repetitions each on the same HBP-AL00 in one sitting;
  the benchmark's caveat about grouped (not interleaved) runs still applies.
- **Elapsed figures are secondary.** For the browser case the declared metric is a count and
  its 66.6% reduction is the number that matters; the elapsed drop is consistent but is not
  what the oracle asks for.
- **`measurements/results.json` has not been rewritten.** It still holds what the original
  session reported. This document and `measurements-staging/` are the new evidence, pending a
  decision to fold them into the published results.
