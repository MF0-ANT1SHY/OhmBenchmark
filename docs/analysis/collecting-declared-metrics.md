# Recipe: collecting a case's declared metric

This is the procedure that produced
`docs/analysis/measurement-statement-count.md` and
`docs/analysis/measurement-query-count.md`. It is what the remaining cases need.

## The problem it solves

Each `cases/<id>/case.json` declares a bespoke `test_oracle.metric`, but the original
reporter chose the measured key from a hardcoded set, so 14 of 17 measured cases reported
`elapsed_ms` regardless. `tools/report_oracle_coverage.py` classifies the gap per case.

## Prerequisites (all present on this machine now)

| Need | Where | Check |
| --- | --- | --- |
| device | HBP-AL00 over `hdc` | `hdc list targets` |
| JRE | `~/.local/jre` | `java -version` |
| toolchain | `toolchain/` -> `/home/research/OhmBenchmark-toolchain` | `hvigorw --version` |
| signing identity | `~/.local/ohsign2` | `python3 device-tests/sign_hap.py prepare` |
| host clone per app | `hosts/<host>` with the case tags | `git -C hosts/<host> tag -l` |
| harness entry | `device-tests/patches/<case>/<variant>.patch` | some cases lack it entirely |

`python3 device-tests/doctor.py` reports all of this in one command.

## Procedure

Use the driver, which does every step per variant:

```bash
bash device-tests/run_declared_metric.sh <case> <host> <unfixed-commit> <fixed-commit> \
     <instrumenter> 3
```

It performs, per variant: hard-reset the host clone to the recorded commit, apply the
measurement patch, run the instrumenter, build, sign, install, then collect N runs into
`measurements-staging/<case>/<variant>/runN/`.

Commits come from `cases/<id>/case.json` (`unfixed_commit`, `fixed_commit`).

## Writing an instrumenter

An instrumenter must add a counter that is **identical in both variants** and changes no
behaviour. Two exist; copy the shape that fits:

- `tools/instrument_statement_count.py` - counts RDB statements around the store calls,
  emits `OHMB/StatementCount`
- `tools/instrument_query_count.py` - counts store reads, emits `OHMB/QueryCount`

Both emit through `hiTraceMeter.traceByValue`, the same mechanism the existing
`ArticleCardCount` / `HistoryItemCount` markers use, so `tools/device/analyze.py` can read
them without changes.

### Two traps, both hit for real

1. **Do not wrap calls in closures.** ArkTS rejects it with `Object is possibly 'null'`
   because the closure hides the store's null-narrowing. *Prepend* a statement instead and
   leave the original expression untouched.
2. **The case `fix.patch` will not apply on top of instrumentation** - line numbers move.
   Take the fixed file from the recorded fixed commit instead:

   ```bash
   git -C hosts/<host> show <fixed-commit>:<path/to/file> > <path/to/file>
   ```

   Then re-apply the counter.

## Reading the result

The marker lands in `measurements-staging/<case>/<variant>/runN/trace.txt.gz`:

```bash
zcat trace.txt.gz | grep -o 'StatementCount|[0-9]*' | tail -1
```

`tools/report_oracle_coverage.py` also reads staged runs, so a case whose declared metric has
been collected shows as `declared-collected-new` with its per-variant values.

## Rules this follows

- **3 repetitions per variant** before any case status changes. One run demonstrates the
  instrumentation; it is not a result.
- New collection goes to `measurements-staging/`; `measurements/` is the untouched
  original session, and the collector refuses to overwrite it.
- A case is only a clear difference when the **declared** metric was collected and the
  unfixed/fixed ranges **do not overlap**.

## Cases still needing an instrumenter

| case | declared metric | primitive to add |
| --- | --- | --- |
| `interviewapp_search_history_sync_flush` | `flush_count_per_search_burst` | count preferences `flush` calls |
| `interviewapp_search_history_unbounded` | `history_entries_and_render_cost` | entry count is already in `result`; add render cost |
| `wanharmony_persisted_home_list_growth` | `persistent_write_bytes_per_loadmore` | I/O byte counter |
| `wanharmony_web_progress_log_storm` | `log_calls_per_pageload` | count log calls at milestones |
| `ytmusic_*` (3 cases) | assorted counts | count JSON parses / search requests / rerenders |

`wanharmony_html_decode_per_render` and `sepweather_font_register_per_page` need a
**bench entry written from scratch** - `device-tests/patches/` has no directory for either,
and no signed build exists for them either.
