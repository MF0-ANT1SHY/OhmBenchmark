# interviewapp_search_history_sync_flush: instrumentation done, measurement blocked

## Where this case stands

The declared metric `flush_count_per_search_burst` now has an instrumenter
(`tools/instrument_flush_count.py`, emits `OHMB/FlushCount`). The **unfixed build compiles
with it** (BUILD SUCCESSFUL) and the counter is correctly placed in the search-burst branch.

The **measurement has not run**: the driver's second (fixed) pass applied
`device-tests/patches/interviewapp_search_history_sync_flush/fixed.patch` incompletely, so
no `OhmProbe.ets` appeared, the bench could not signal `state=ready`, and all three runs timed
out. No declared-metric values were collected for this case.

## An oracle correction this case needs

The oracle states:

> unfixed: 10 flushes (one per search); fixed: 1 flush after the burst

but the harness drives **1000** `setItem` calls per burst, and unfixed `setItem` calls
`this.store.flush()` on every one. The expected unfixed count is therefore **1000**, not 10;
the oracle's figure is written for a 10-search burst this fixture does not use. The
comparison's *direction* (unfixed flushes once per search, fixed flushes once after the
burst) is still right. This needs an `oracle_revision` entry once the measurement confirms
the numbers, in the same style as the four equivalent-oracle renames.

## The open problem

`git apply --check` **succeeds** for both the unfixed and fixed patches against their
respective commits when run by hand from a clean tree, yet the driver's fixed pass reported
`WARNING: no OhmProbe after applying the patch` and the instrumenter then found only 1 of the
2 flush call sites (the fixed source has two: `scheduleFlush`'s timer callback and
`delItem`/`setItem` through it). So the apply is failing in the driver's context for a reason
not yet identified.

Candidate causes to check next, in order of likelihood:

1. **`git -C "$H" apply` resolves the patch path before the `cd`** - the driver builds an
   absolute path, so this should be safe, but the earlier relative-path bug was the same
   class, so verify by echoing the path and `ls -l` on it at that point.
2. **`git clean -fd` removing a directory the patch expects to create into.** The fixed patch
   creates `features/home/src/main/ets/utils/OhmProbe.ets`; if `clean` removes an empty
   parent directory that the checkout left behind, the apply could fail.
3. **The unfixed pass leaving the tree dirty in a way that survives into the fixed pass** -
   the driver checks out `--force` and cleans, so this should not happen, but the
   instrumenter's added files are untracked and `clean` handles them only if `-x` is used
   (it is not). An untracked `history.ets` companion from the unfixed pass could collide.

The quickest diagnostic is to make the driver print `git apply`'s own exit code and stderr
instead of swallowing them, then re-run the fixed pass alone.

## Verified so far for this case

- `tools/instrument_flush_count.py` is idempotent and rewrites exactly the 2 unfixed flush
  call sites, routing them through a counting wrapper that does not recurse.
- `HistoryStore` is module-private in `history.ets`; the count is exposed through exported
  `resetOhmFlushCount()` / `getOhmFlushCount()` accessors because the bench cannot reference
  a class static.
- The reset and marker land in the search-burst branch, identified by the deferred-flush
  wait that only that branch has.
- The host needs `ohpm install --all` before it compiles; the driver now does this.
