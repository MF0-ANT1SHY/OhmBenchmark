# interviewapp_search_history_unbounded: declared metric measured

## Declared metric

`history_entries_and_render_cost` - "Number of history entries retained after 60 searches,
size of the preferences file, and CPU/time to render the history component when the search
page opens."

The bench returns `getAll().length` summed over 100 calls, which is that entry count directly.
**No instrumentation was needed** - the harness already returned the declared quantity and
the reporter simply never used it. This is the clearest instance of the `collected-not-used`
finding: the measurement existed, the will to report it did not.

## Result (3 repetitions per variant, builds from the recorded commits)

| variant | entries retained | elapsed |
| --- | --- | --- |
| unfixed | **500000, 500000, 500000** | 442 ms (median) |
| fixed | **2000, 2000, 2000** | 10 ms (median) |

- median reduction **99.6%** on the declared metric, **97.7%** on elapsed
- **ranges do not overlap**, zero spread either side
- 500000 = 5000 retained entries x 100 reads; 2000 = 20 retained entries x 100 reads, i.e.
  exactly the oracle's "unfixed retains 60+ entries and growing; fixed retains 20"
- these figures match the recorded original session (500000 / 2000), so the case reproduces

## Note on the oracle's "60 searches"

The oracle describes 60 searches, while the fixture seeds 5000 entries in preparation and
performs 100 reads in the measured phase. The *comparison* - unbounded retention versus a
20-entry cap - is exactly what the numbers show, so the claim holds; only its framing in terms
of "60 searches" does not match the fixture. Recorded here rather than silently re-declared,
because unlike the flush case the comparison itself needs no correction.

## What this establishes

The declared metric is genuinely collected and the builds separate by 250x on it. All four
cases originally classified `collected-not-used` now have measured declared metrics:

| case | declared metric | unfixed -> fixed |
| --- | --- | --- |
| `browser_insert_date_lookup_cache` | statements per save | 3000 -> 1002 |
| `sheafreader_unread_counts_n_plus_1` | queries per refresh | 201 -> 2 |
| `interviewapp_search_history_sync_flush` | flushes per burst | 1000 -> 1 |
| `interviewapp_search_history_unbounded` | entries retained | 500000 -> 2000 |

## What it does not establish

One device, one session, grouped rather than interleaved runs.
`measurements/results.json` has deliberately not been rewritten.
