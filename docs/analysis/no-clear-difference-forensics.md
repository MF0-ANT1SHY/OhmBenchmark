# Why 17 cases did not reach a clear difference

Scope: the 30-case dataset. 13 reached "明确差异" (clear difference); 17 did not.
This note records the cause for each of the 17, separating **case/patch design** from
**test/measurement design** from **environment/tooling** from **budget**.

## Evidence sources

| Source | What it is |
| --- | --- |
| `measurements/results.json` | final per-case status (run on the Pura 70, Windows host, 2026-10-01) |
| `measurements/summary.json` | 102 per-round records; a case has 6 rounds iff it was formally measured |
| `measurements/experiments/` | excluded pilot/exploratory runs with written verdicts |
| git branch `dev/proof-loop` → `results/campaign.jsonl` | macOS automated campaign: 18 BLOCKED / 10 EXECUTABLE |
| git branch `dev/proof-loop` → `results/device_run.jsonl` | 187 per-step device operations incl. errors |
| git branch `dev/proof-loop` → `results/proof.jsonl` | 19 proof-loop attempts: 11 FAIL / 7 BLOCKED / 1 PASS |
| `device-tests/patches/<case>/{unfixed,fixed}.patch` | the measurement-entry harness injected per case |
| `cases/<case>/fix.patch`, `cases/<case>/case.json` | the bug fix and its declared oracle |

## Headline finding

**The 13 that worked prove the patches work.** Each shows a large, non-overlapping effect.
For the failing 17, the dominant cause is **not** defective patches. It is, in order:

1. **Budget** — the measurement window was a 3-hour budget (00:57:57 → 03:57:57 Beijing, stated
   in the generated report). 102 rounds x 6 per case = 17 cases fit. 30 did not.
2. **Environment/tooling** — the macOS campaign blocked 18/28 cases on defects that were
   later worked around for the cases that did get measured.
3. **Test/measurement design** — for the 4 measured-but-no-effect cases the oracle and the
   workload do not line up; one case is unfalsifiable by construction.
4. **Case/patch design** — affects a minority; detailed in the companion analysis.

## Taxonomy of the 17

### A. Never measured (12) — no formal rounds recorded

| Case | Runs | Reached launch | Cause |
| --- | --- | --- | --- |
| cloudmusic_indexof_in_render | 7 | yes | host instability: unsigned-HAP install + dirty `oh-package-lock.json5` blocks checkout + API server unreachable |
| cloudmusic_play_time_high_frequency_update | 7 | yes | same host instability |
| cloudmusic_search_result_foreach | 7 | yes | same host instability |
| cloudmusic_songcard_artists_concat | 5 | yes | same host instability |
| ytmusic_current_playing_timeupdate | 6 | yes | host repo absent on the measurement machine (`pathspec ... did not match`) |
| ytmusic_history_json_parse_per_row | 5 | yes | same |
| ytmusic_search_no_debounce | 4 | yes | same |
| wanharmony_html_decode_per_render | 9 | **all 9 ok** | ran cleanly; formal rounds never produced — budget / pipeline gap |
| wanharmony_persisted_home_list_growth | 4 | **all 4 ok** | same |
| wanharmony_web_progress_log_storm | 4 | **all 4 ok** | same |
| sepweather_font_register_per_page | 6 | **all 6 ok** | same |
| weatherassistant_remote_weather_icons | 2 | no | injected `.cjs` module-resolution error |

Note: `cloudmusic_local_song_memory_filter` was measured successfully on the *same* host that
blocked its four siblings — so the CloudMusic blocks were workable, not fundamental.

### B. Measured but no stable improvement (4)

| Case | Oracle metric (declared) | Reported metric | Effect | Cause |
| --- | --- | --- | --- | --- |
| sheafreader_article_list_foreach | `article_row_build_count` | `elapsed_ms` | +0.0% | **unfalsifiable by construction**: the harness holds a fixed 10 s window, so `elapsed_ms` is ~10000 ms in every run by design. The declared signal (component builds) was flat at 37 in both variants, contradicting the case.json claim |
| cloudmusic_local_song_memory_filter | `search_result_latency_ms` | `elapsed_ms` | -12.3% | workload too small: the buggy method is invoked only ~10x; per-call cost is 24-110 ms with variance exceeding the effect |
| sheafreader_insert_duplicate_exception | `no_op_refresh_cpu_ms` | `elapsed_ms` | +4.9% | wrong quantity measured: a 22.6-35.6 s wall window dominated by fixture/transaction work; the declared CPU-of-no-op-refresh was never isolated. Unfixed range spread 58% |
| weatherassistant_http_session_leak | `retained_fds_and_connections` | `elapsed_ms` | +0.6% | condition not established: 120 fresh-process requests produced **zero** fd growth (71→71, 79→79) in both variants, contradicting the ~1-fd-per-request leak claim |

### C. Blocked (1)

| Case | Cause |
| --- | --- |
| interviewapp_response_log_full_stringify | the local fixture response arrives as a string over the native HTTP path, so the original success-code check rejects it before the logging code runs; recorded as blocked, and no response-normalisation change was made to force the path |

## Cross-cutting defect: the oracle is not the measured quantity

For **all 17** measured cases the metric reported in `results.json` differs from the
`test_oracle.metric` declared in `cases/<id>/case.json`:

- 14 report the generic harness timer `elapsed_ms`
- 3 report `trace_cpu_ms`
- 0 report their declared oracle metric

`device-tests/export_results.py` selects the key with a hardcoded set:
`cpu_cases = {browser_eager_history_load, browser_history_list_foreach,
interviewapp_search_history_sync_flush}`; everything else falls back to `elapsed_ms`.
The prose in the generated report discloses that some cases use a proxy measurement path.
This is the single largest systematic weakness, because four of the failing cases fail
*together with* a declared oracle that was never actually collected.

## The campaign's BLOCKED verdicts are not a valid excuse

`results/campaign.jsonl` recorded 18 of 28 cases BLOCKED. **8 of those 18 were subsequently
measured successfully** on the Pura 70:

```
interviewapp_search_history_sync_flush      jingmo_dataset_import_no_transaction
interviewapp_search_history_unbounded       jingmo_random_poem_orderby_random
                                            jingmo_sync_page_reimport
                                            sheafreader_extract_tag_tolowercase
                                            sheafreader_refresh_feeds_sequential
                                            sheafreader_unread_counts_n_plus_1
```

Each of those 8 blocked with `[Errno 2] No such file or directory: .../hosts/<host>/entry/src/main/module.json5`
or an unsigned-HAP install failure. Those were harness/path/signing defects, not case defects:
the same cases ran once the host layout and signing were fixed. So the macOS campaign
**understates** what is achievable, and the CloudMusic/YTMusic blocks of the same character
should be treated as fixable rather than as evidence against the cases.

Dispatch coverage was not the limiting factor either: every one of the 30 cases has
`device_run` records (98 for the 13 clear cases, 89 for the 17 that did not).

## What was excluded, and why (from measurements/experiments/)

These written verdicts show the effect-size floor being applied honestly:

- `browser_startup_10000_rows` — non-overlapping but ~17.8% median reduction, below the >=20% oracle
- `sheafreader_parser_ascii` — ~2% wall, ~8% CPU, below the 15% oracle
- `sheafreader_parser_300_freeze` — unfixed froze (THREAD_BLOCK_6S) and exited; re-run at 100 articles
- `wan_history_50000_incomplete` — process disappeared before the measured op completed; re-run at 5,000 records
- `sheafreader_duplicate_before_screen_control` — screen timeout corrupted fixed run 1; re-run with wake lock
- `jingmo_concurrent_report_excluded` — fixed series overlapped an on-device report job; re-run clean
- `cloudmusic_install_failure_mislabeled` — first signing attempt had no destination dir; unfixed app stayed installed and was mislabelled fixed
- `cloudmusic_first_series_missing_marker` — first unfixed round had no OHMB boundary; all three retained and recollected
- `interview_probe_initialization` — probe statically imported the home module, initialising HistoryStore without a UI context
- `response_overlimit` — 10.5 MB pilot exceeded the native 5 MiB HTTP limit; then the 3.5 MB fixture still arrived as a string and was rejected

## Recoverability

The released proof traces (`device-proof-2026-09-24`, 182 assets) contain **zero** `OHMB/`
markers, i.e. they come from the macOS proof loop and not from the measurement harness.
They therefore cannot be analysed offline to yield harness-equivalent metrics; the cases
above need genuine re-runs of the measurement harness.
