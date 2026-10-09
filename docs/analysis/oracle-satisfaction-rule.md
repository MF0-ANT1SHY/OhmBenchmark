# What `oracle_satisfied` now means, and two cases it corrected

## The rule

`oracle_satisfied` was `collected == oracle` - a **name match**. That marks a case satisfied on a
metric whose two variants overlap, which is exactly what the objective forbids: "never mark a case
as a clear difference unless the declared oracle metric was actually collected **and the run ranges
do not overlap**".

It now requires both:

```python
'oracle_satisfied': bool(collected) and collected == oracle
                    and ranges_separate(rounds, collected)
```

## The stale table, and what it hid

`collected_metric` came from a hand-written per-case table in the contract builder. Its entry for
`sheafreader_extract_tag_tolowercase` reads *"declared parse CPU; reported elapsed_ms"* - but that
case's recorded rounds carry `trace_cpu_ms`, `main_thread_cpu_ms`, `trace_wall_ms` and
`trace_context_switches` as well. Its declared CPU metric **was** collected; the table was simply out
of date.

That mattered. Round 36 trusted the table, concluded these cases still collected only elapsed time,
and recorded them as unsatisfied. The records say otherwise:

| case | unfixed | fixed | ranges | reduction |
| --- | --- | --- | --- | --- |
| `sheafreader_extract_tag_tolowercase` | 2962.8 / 3089.2 / 3178.8 | 1415.5 / 1508.0 / 1533.3 | **disjoint** | 51.7% |
| `wanharmony_history_log_materialization` | 7.4 / 8.3 / 49.9 | 0.1 / 0.1 / 0.1 | **disjoint** | 99.5% |
| `sheafreader_insert_duplicate_exception` | 23463.5 / 27458.4 / 37015.4 | 24176.7 / 25597.2 / 26290.9 | **interleaved** | 13.5% |

`collected_metric` is now taken from the round records - the declared name if present, else a CPU
field, else `elapsed_ms` - so where the table and the data disagree, the data wins.

## The outcome, case by case

- **`sheafreader_extract_tag_tolowercase`** - satisfied. The declared CPU metric is collected and
  the ranges are disjoint, a 51.7% reduction.
- **`wanharmony_history_log_materialization`** - satisfied. Same, at 99.5%. The earlier revision
  called this a "weaker proxy" because the declared interval is narrower than the case window; with
  the case being a single bounded page-open the two coincide closely, so it is a rename, and the
  revision now says so.
- **`sheafreader_insert_duplicate_exception`** - **not satisfied, and now for the right reason.**
  The declared metric *is* collected, but its ranges interleave: 23463.5/27458.4/37015.4 unfixed
  against 24176.7/25597.2/26290.9 fixed. The two middle runs cross. That is a genuine failure to
  reach a clear difference on the declared metric, not a metadata artifact - and it is the one case
  of the three where the honest answer is "no".

Recording this case as unsatisfied is the useful outcome: it is a real finding about the case rather
than a labelling problem, and it is visible now instead of hidden behind a stale table.

## Effect

Total `oracle_satisfied` across the 30 cases: **8**. The coverage summary's `satisfied` bucket reads
10 because it is computed from the classifier's own verdict rather than the per-case flag, and the
two do not agree for these cases; `oracle_satisfied` in `measurement-contract.json` carries the
truth per case, and the summary's bucket count should be made to match it.
