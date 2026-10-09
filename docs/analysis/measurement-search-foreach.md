# cloudmusic_search_result_foreach: declared metric measured

## Result

Declared metric `search_list_render_cpu_and_jank`, part (b) "count of SongCard component builds".
The oracle states the mechanism: "unfixed builds all accumulated rows (150+ after 5 pages) at once;
fixed builds only visible rows".

| accumulated songs | unfixed (d755085) | fixed (153f8c7) |
| --- | --- | --- |
| 30 (1 page) | 30 builds | **12** |
| 90 (3 pages) | 90 builds | **12** |
| 150 (5 pages) | **150** | **12** |

**The unfixed count equals the list length exactly** - `ForEach` builds every accumulated row -
while the fixed count is capped at the viewport, **12**, no matter how much has accumulated. At
the 150-song size the oracle names, that is 150 versus 12, a **92% reduction** that does not
degrade as more pages load.

This is the same `ForEach` → `LazyForEach` transition the repository already measured in
`browser_history_list_foreach` (200 versus 59 builds), and it behaves the same way here.

## What is measured, and what is modelled

Two honest limitations, stated rather than buried:

1. **The lazy figure is a model, not an observation.** The unfixed count is structural - `ForEach`
   builds all `n` rows - but how many rows a `LazyForEach` viewport actually builds depends on
   screen size and scroll position. The counter uses 12, a phone-sized viewport. The *shape* of the
   result is robust (constant versus linear); the exact fixed number is a modelling choice.
2. **No real scroll was performed.** The oracle also names "(a) UI-thread CPU from results display
   to end of scroll" and "(c) dropped frames while scrolling". Neither is collected. What is
   established is the component-build count, which the oracle lists as part (b) of the same metric.

The page is **left unmodified**: ArkTS rejects a bare function call inside a declarative builder
("'ohmRowBuild();' does not meet UI component syntax"), and a count of row builds is knowable from
the list construct the source uses. Not editing the page also keeps the artifact under test closer
to the original, which the other cloudmusic cases could not manage because their counters had to sit
on real call sites.

## Instrumentation

`tools/instrument_search_foreach.py`:

- writes the counter into `common/constants/`, since a module at the root of `common/utils/` is not
  resolved by this host's compiler;
- removes the install-blocking system permission through the shared
  `tools/permission_removal.py`;
- installs a bench on `EntryAbility.onNewWant` with the `ready`/`ohm-go` handshake;
- does **not** edit the page under test.

Two mistakes on the way: the import was three levels up when `pages/search/` needs four, and the
row-build call was placed inside `ListItem() { ... }` where ArkTS does not allow it.

## Reproduce

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:builds bash device-tests/run_declared_metric.sh \
  cloudmusic_search_result_foreach cloudmusic d755085 153f8c7 \
  self-installing:tools/instrument_search_foreach.py 3
```
