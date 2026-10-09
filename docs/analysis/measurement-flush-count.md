# interviewapp_search_history_sync_flush: declared metric measured

## Declared metric

`flush_count_per_search_burst` - preference flush (disk write) operations the history store
performs during a search burst. Instrumented as `OHMB/FlushCount` by
`tools/instrument_flush_count.py`.

## Oracle correction

The original comparison read "unfixed: 10 flushes (one per search); fixed: 1 flush after the
burst". The harness drives **1000** `setItem` calls, and unfixed `setItem` calls
`this.store.flush()` on every one, so the count for this fixture is 1000, not 10 - the
original figure describes a 10-search burst the fixture does not use. The claim's direction
(per-save flush versus a single deferred flush) is unchanged. Recorded in
`test_oracle.oracle_revision`.

## Result (3 repetitions per variant, builds from the recorded commits)

| variant | flushes | elapsed |
| --- | --- | --- |
| unfixed | **1000, 1000, 1000** | 8.3 s (median) |
| fixed | **1, 1, 1** | 3.1 s (median) |

- median reduction **99.9%** on the declared metric, **62.6%** on elapsed
- **ranges do not overlap**, zero spread either side
- the fixed count of exactly 1 is what the corrected oracle predicts: the debounce timer
  fires once during the bench's 3s post-burst wait

## Instrumentation note

The marker must be sampled **after** the deferred-flush wait. Placed before it, the fixed
build reads 0 - the debounce has not fired yet - which is how the first attempt produced
"unfixed 1000, fixed 0" even though the fix was working. That is a genuine measurement trap
for any debounced behaviour.

## What this establishes

The declared metric is now genuinely collected and the two builds separate completely on it.
Together with `browser_insert_date_lookup_cache` (3000 vs 1002 statements) and
`sheafreader_unread_counts_n_plus_1` (201 vs 2 queries), three cases have moved from
`collected-not-used` to measured declared metrics.

## What it does not establish

One device, one session, grouped rather than interleaved runs. `measurements/results.json`
has deliberately not been rewritten; this document and `measurements-staging/` are the new
evidence.
