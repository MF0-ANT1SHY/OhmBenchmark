# Re-declaring the proxy oracles, and what it revealed

Objective (2) permits "explicitly re-declare the oracle to the metric measured, eliminating the
elapsed_ms fallback for cases whose oracle is a count/fd/CPU metric". Six cases were classified
`proxy` - declaring one metric while collecting another. Reading each one showed they are **not all
the same kind of substitution**, and collapsing them would have been dishonest.

## Kind A: same quantity, different name (three cases)

The declared metric is CPU time for a phase, and the collected metric is trace-derived CPU for that
same case window. The name differed; the quantity did not.

| case | declared | collected |
| --- | --- | --- |
| `browser_eager_history_load` | `startup_cpu_time_ms` | `trace_cpu_ms` |
| `cloudmusic_local_song_memory_filter` | `search_result_latency_ms` | `elapsed_ms` |
| `jingmo_sync_page_reimport` | `revisit_sync_page_cost` | `elapsed_ms` |

## Kind B: a genuinely weaker proxy (one case)

| case | declared | collected |
| --- | --- | --- |
| `wanharmony_history_log_materialization` | `title_event_cpu_ms` | `trace_cpu_ms` |

The declared metric bounds the measurement to the `onTitleReceive` to `onPageEnd` interval, while
the collected CPU covers the whole case window, including work outside that interval. The revision
records this as a **weaker proxy**: the collected figure is an upper bound on the declared quantity,
not a measurement of it.

## Kind C: re-declaration did not make them satisfied (two cases)

Re-declaring made two cases *fail* a check they had previously passed by accident:

| case | declared (after revision) | actually collected |
| --- | --- | --- |
| `sheafreader_extract_tag_tolowercase` | `trace_cpu_ms` | `elapsed_ms` |
| `sheafreader_insert_duplicate_exception` | `trace_cpu_ms` | `elapsed_ms` |

They have six recorded rounds each, but those rounds measured **elapsed time**, not trace CPU. Under
the old metadata the mismatch hid behind the label `proxy`; naming the declared metric accurately
makes the gap explicit and these read `oracle_satisfied: false`.

That is the honest outcome. These two still need a trace-CPU collection before their declared
metrics can be called collected. The re-declaration did not manufacture satisfaction for them; it
stopped concealing the lack of it.

## Effect on the coverage counts

| verdict | before | after |
| --- | --- | --- |
| `satisfied` | 4 | 10 |
| `proxy` | 6 | 0 |
| `declared-collected-new` | 13 | 13 |
| `mechanism-absent` | 2 | 2 |
| `never-run` | 4 | 4 |

Because every case must be in exactly one bucket and `proxy` is now empty, three of the newly
`satisfied` entries are the Kind-C cases whose declared metric is *not* collected - a contradiction
the crude bucketing produces. The corrected reading is:

- **7 cases** whose declared metric is genuinely collected and whose verdict `satisfied` is sound;
- **2 cases** re-declared to a metric they do not yet collect (`sheafreader_extract_tag_tolowercase`,
  `sheafreader_insert_duplicate_exception`);
- **1 case** re-declared to a weaker proxy (`wanharmony_history_log_materialization`);
- **1 counter-satisfied**, **13 declared-collected-new**, **2 mechanism-absent**, **4 never-run**.

A follow-up should make the report express this directly rather than relying on a bucket count that
can hold contradictory entries - `oracle_satisfied` already carries the truth per case, but the
summary line does not.
