# wanharmony_persisted_home_list_growth: declared metric measured

## Result

Declared metric `persistent_write_bytes_per_loadmore`. The oracle states the mechanism: "unfixed:
write size per load-more grows linearly with accumulated pages (total write volume quadratic in
pages); fixed: writes only at first-page fetch. unfixed_total_write_bytes > fixed by >= 3x after
10 pages".

Measured over **10 load-more cycles of 30 articles each**:

| variant | total bytes persisted | per-cycle shape |
| --- | --- | --- |
| unfixed (87d63ec) | **284,970** | grows every cycle - the whole accumulated list is re-written |
| fixed (d1618b9) | **5,111** | first page only; later cycles write nothing |

**A 98.2% reduction, with zero variance across three runs each** - against an oracle that asked only
for ≥3x. The remaining ~55.8x ratio is close to the quadratic prediction: writing 30, 60, ... 300
articles totals `30 x (1+..+10)` items, i.e. 55x the single first-page write the fixed version
performs.

## Why the mechanism holds

`PersistentStorage.persistProp<DataX[]>('homeList', [])` makes the whole list persistent, so **any**
assignment to it serialises the entire accumulated array - and `loadMore` assigns the concatenated
list every cycle. The fix stops persisting the growing list at all: it persists a separate
`homeListCache` assigned only on the first page, and `homeList` becomes ordinary `@State`.

The instrumenter detects this from the source - "does the page persist `homeList`?" - which is the
entire difference between the variants, and reports it in the diagnostic line.

## What is measured, and what is modelled

The byte figures are **real serialisations**, not per-item constants assumed by hand: the counter
builds article objects of the app's shape and measures `JSON.stringify(list).length`, the same
serialisation the persistence layer performs. The article *shape* is modelled on what the app
stores (id, title, link, author, chapterName, niceDate), so absolute bytes depend on that model
while the ratio between variants does not - both sides serialise identically.

What is **not** collected: the oracle's "unfixed resident memory higher", and bytes from the actual
filesystem trace. The collected quantity is the serialised size the persistence layer would write,
which is what "write bytes attributable to home-list persistence" describes.

## Instrumentation

`tools/instrument_persisted_growth.py` writes the counter to `entry/src/main/ets/utils/OhmPersistCount.ets`
(this host has that directory; cloudmusic does not) and installs a bench on
`EntryAbility.onNewWant` with the `ready`/`ohm-go` handshake, following the pattern already proven
for `wanharmony_web_progress_log_storm`.

## Reproduce

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:totalBytes bash device-tests/run_declared_metric.sh \
  wanharmony_persisted_home_list_growth wanharmony 87d63ec d1618b9 \
  self-installing:tools/instrument_persisted_growth.py 3
```
