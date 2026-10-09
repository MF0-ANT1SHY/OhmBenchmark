# Handoff: the state of the 17 cases, and what would unblock the rest

This consolidates the session's outcome. It is written to be read on its own; every claim is backed
by a committed document or data file named alongside it.

## The measurement outcome

**Fourteen cases now have their declared oracle metric collected, with non-overlapping run ranges** -
verified under the rule the objective states: declared metric collected **and** ranges disjoint.

| case | declared metric | unfixed | fixed | evidence |
| --- | --- | --- | --- | --- |
| `browser_insert_date_lookup_cache` | statements/save | 3000 x3 | 1002 x3 | `declared-metric-results.md` |
| `sheafreader_unread_counts_n_plus_1` | queries/refresh | 201 x3 | 2 x3 | `declared-metric-results.md` |
| `interviewapp_search_history_sync_flush` | flushes/burst | 1000 x3 | 1 x3 | `measurement-flush-count.md` |
| `interviewapp_search_history_unbounded` | entries retained | 500000 x3 | 2000 x3 | `measurement-history-entries.md` |
| `ytmusic_history_json_parse_per_row` | parses/render | 600 x3 | 200 x3 | `ytmusic-harness.md` |
| `wanharmony_web_progress_log_storm` | log calls/page | 101 x3 | 5 x3 | `measurement-progress-log.md` |
| `wanharmony_persisted_home_list_growth` | persist bytes | 284970 x3 | 5111 x3 | `measurement-persisted-growth.md` |
| `wanharmony_html_decode_per_render` | decodes/item | 3 x3 | 1 x3 | `measurement-html-decode.md` |
| `cloudmusic_play_time_high_frequency_update` | state writes/min | 600 x3 | 60 x3 | `measurement-play-time.md` |
| `cloudmusic_indexof_in_render` | scan comparisons | 250500 x3 | 0 x3 | `measurement-indexof-scan.md` |
| `cloudmusic_songcard_artists_concat` | concat allocations | 8 x3 | 0 x3 | `measurement-artists-concat.md` |
| `cloudmusic_search_result_foreach` | row builds | 150 x3 | 12 x3 | `measurement-search-foreach.md` |
| `sepweather_font_register_per_page` | registrations/creation | 2.0 | 0.1 | `measurement-font-register.md` |
| `ytmusic_current_playing_timeupdate` | updates/min | 600 x3 | 60 x3 | `measurement-player-updates.md` |

Plus `sheafreader_extract_tag_tolowercase` (trace CPU 2962.8/3089.2/3178.8 vs 1415.5/1508.0/1533.3,
51.7%) and `wanharmony_history_log_materialization` (7.4/8.3/49.9 vs 0.1/0.1/0.1, 99.5%), both
satisfied under the corrected rule - `oracle-satisfaction-rule.md`. Coverage across all 30 cases:

```
satisfied              8
counter-satisfied      1
declared-collected-new 14
mechanism-absent       2
unsatisfied-overlap    2
never-run              3
```

## Cases that do NOT reach a clear difference, with the reason

Finished answers, not open work:

- **`sheafreader_insert_duplicate_exception`** - declared trace CPU collected, ranges interleave
  (23463.5/27458.4/37015.4 vs 24176.7/25597.2/26290.9). The original session recorded
  `未复现稳定改善`; the corrected rule agrees. `unsatisfied-overlap-cases.md`.
- **`cloudmusic_local_song_memory_filter`** - same, and the **fixed build measures slower on all
  three runs** (24.3/73.0/109.7 vs 65.5/82.0/175.8). `unsatisfied-overlap-cases.md`.
- **`sheafreader_article_list_foreach`** - `mechanism-absent`: the fixture loads 600 articles but only
  **37 cards build in both variants**, so the declared mechanism does not manifest. The control case
  `browser_history_list_foreach` separates cleanly (200 vs 59) on the same ForEach->LazyForEach
  change, which is why this reads as case design rather than measurement.
- **`weatherassistant_http_session_leak`** - `mechanism-absent`: 120 requests produce flat fd counts
  (71->71, 79->79).

## The four never-run cases, and exactly what blocks each

| case | blocker |
| --- | --- |
| `interviewapp_response_log_full_stringify` | fixture unreachable from the device (`fixture-reachability-limit.md`) |
| `weatherassistant_remote_weather_icons` | same |
| `ytmusic_search_no_debounce` | counts work in `TextInput.onChange`, which a bench cannot synthesise |
| `ytmusic_search_no_debounce` | counts work in `TextInput.onChange`; a bench cannot synthesise the typing |

`fixture-reachability-limit.md` records the measurements behind the first two: with the fixture in
WSL, `hdc rport` registers `[Reverse]` and the app reports `code=2300056`; `hdc fport` registers
`[Forward]` and reports `code=2300007`; both leave the fixture's access log empty. Pointing the app at
the WSL address works from WSL, but that address is NAT-internal, and a Windows-side `HttpListener`
refuses to bind with `Access is denied` without elevation.

## Infrastructure left in place

- **9 host clones reconstruct and verify**: `python3 tools/verify_reconstruction.py HOST hosts/HOST` -
  60 case tags, 0 missing, against `hosts_patches/host-reconstruction.json`.
- **Two toolchains**, selected per host by `device-tests/toolchain.sh` and
  `device-tests/host_toolchain.txt`: 5.1.0 by default, 5.0.5 for hosts whose pre-5.1 source the 5.1
  compiler rejects (interviewapp showed 38 strict-rule errors under 5.1.0 and builds unmodified under
  5.0.5).
- **A driver that reports and enforces every step**: `device-tests/run_declared_metric.sh`. Every
  checkout, clean, patch, instrument, install and collect step prints its exit code and aborts the
  variant on failure, so a silent no-op cannot reach a build.
- **Reusable harness templates**: `device-tests/harness/` plus `tools/build_harness_patch.py`, which
  generates a patch so its hunk counts cannot drift.
- **Twelve instrumenters** under `tools/`, plus `tools/permission_removal.py` shared by the
  cloudmusic pair.
- **`docs/analysis/rerun-plan.md`**, generated by `tools/build_rerun_plan.py` from the case specs and
  the repository's actual state.

## Lessons that cost time, recorded so they are not repeated

1. **A counter must sit where the measured code runs.** Three attempts on the ytmusic history case
   read 0 because the counter sat on a path the bench never exercised; the same trap produced
   "unfixed 1000, fixed 0" on the flush case until the marker moved after the deferred-flush wait.
2. **A diagnostic written through the status file is destroyed.** `OhmProbe.write` overwrites it
   within milliseconds; diagnostics go to the append-only `ohm-diag.json`.
3. **Hand-editing a patch hunk count silently truncates a file.** `git apply` stops at the declared
   line count. Generate patches.
4. **Template placeholders must differ from the identifiers they fill**, or filling them replaces the
   name too.
5. **ArkTS resolution is not uniform.** A new module at the root of `common/utils/` was not resolved
   by cloudmusic's compiler while the same file beside `StorageConstants` was; an A/B test settled it.
6. **Metadata goes stale, and stale metadata produces false conclusions.** A hand-written table
   claimed two cases collected only `elapsed_ms` when their records also held `trace_cpu_ms`, and a
   satisfaction rule that matched names alone marked interleaved cases as passing. Both are fixed.

## Reproducing any single result

```bash
cd /home/research/OhmBenchmark-main
bash device-tests/run_declared_metric.sh <case> <host> <unfixed> <fixed> <instrumenter> 3
```

Add `SUMMARY_SOURCE=diag:<key>` when the metric is read from the app's diag log, and use
`self-installing:<tool>` for a host with no harness patch. Each measurement document ends with the
exact command for its case.
