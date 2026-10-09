# browser_insert_date_lookup_cache: declared metric now measured

## Why this case was not "clear difference"

It declared `rdb_statements_per_page_save`, but `export_results.py` reported `elapsed_ms`
because the key came from a hardcoded set. The declared quantity was never collected, so the
coverage report called it `collected-not-used`.

## What the oracle predicts

From `cases/browser_insert_date_lookup_cache/case.json`:

> unfixed: >= 3 statements per page save after the first (SELECT + CREATE TABLE + INSERT);
> fixed: 1 statement per page save (INSERT only)

## Instrumentation

`RdbUtils.insertDate` runs a `date_table` SELECT, a conditional INSERT, and
`createHistoryTable` (CREATE TABLE IF NOT EXISTS) on **every** save. The fix adds a
`knownDates` cache, so after the first save for a date only the history INSERT remains.

`tools/instrument_statement_count.py` adds a measurement-only counter around those four
operations and emits the tally as an `OHMB/StatementCount` trace marker - the same
mechanism the existing `ArticleCardCount` / `HistoryItemCount` markers use, so
`tools/device/analyze.py` can read it. The counter wraps calls that already happen and
changes no SQL, no control flow and no caching, and **both variants get the identical
counter**, so the comparison stays fair.

## Result (one run each, Pura 70, instrumented builds built from the recorded commits)

| variant | `OHMB/StatementCount` | elapsed |
| --- | --- | --- |
| unfixed | **3000** | 7080 ms |
| fixed | **1002** | 2574 ms |

3000 = 1000 saves x (SELECT + CREATE TABLE + INSERT), exactly the predicted shape. The
fixed build's 1002 is 1000 history INSERTs plus the 2 that the first save for the date still
pays (its cache entry is added only after that first pass), against a predicted 1000.

## Status

The declared metric is now genuinely collected and the two builds separate by ~3x on it.
This is one run per variant, so it is evidence that the instrumentation works, **not yet a
three-repetition claim**: the case needs 3 runs per variant before its status changes.
