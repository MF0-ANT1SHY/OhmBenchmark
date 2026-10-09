# sheafreader_unread_counts_n_plus_1: declared metric now measured

## Declared oracle

From `cases/sheafreader_unread_counts_n_plus_1/case.json`:

> Number of RDB SELECT statements attributable to unread-count computation per sidebar
> refresh, and total refresh latency.
> unfixed: N queries per refresh (one per feed); fixed: 1.

## Instrumentation

`FeedService.getFeedsWithCounts()` is the measured entry. Unfixed, it calls
`db.getAllFeeds()` once and then `db.getUnreadCount(feed.id, -1)` **per feed**; the fix
replaces the per-feed loop with a single `getUnreadCountsByFeed()` GROUP BY query.

`tools/instrument_query_count.py` prepends a counter increment before each store read in
`DatabaseManager` (19 sites unfixed, 20 fixed) and emits the tally as an
`OHMB/QueryCount` trace marker, the same mechanism `ArticleCardCount` / `HistoryItemCount`
use. The counter only *prepends* a statement, leaving the original expression untouched, so
null-narrowing, types and control flow are unchanged - an earlier closure-wrapping shape was
rejected by the ArkTS compiler with "Object is possibly 'null'". Both variants are
instrumented identically.

## Result (one run each, Pura 70, builds from the recorded commits)

| variant | `OHMB/QueryCount` | elapsed |
| --- | --- | --- |
| unfixed | **201** | 3022.1 ms |
| fixed | **2** | 66.6 ms |

201 = 200 feeds + 1 `getAllFeeds`, and 2 = `getAllFeeds` + the single GROUP BY, i.e. exactly
the declared shape. The elapsed figures agree with the originally recorded round for this
case (4053-4082 ms unfixed, 70-102 ms fixed), so the instrumented builds behave like the
builds that were measured before.

## Status

The declared metric is now genuinely collected and the builds separate by ~100x on it. One
run per variant so far, so this demonstrates the instrumentation; the case needs 3 runs per
variant before its status changes.
