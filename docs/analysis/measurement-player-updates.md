# ytmusic_current_playing_timeupdate: declared metric measured

## Result

Declared metric `player_page_updates_per_minute`. The oracle states "unfixed ~600 updates/minute vs
fixed ~60/minute", and the measurement lands on both figures exactly:

| variant | page state updates per minute |
| --- | --- |
| unfixed (c4b1879) | **600** |
| fixed (e175817) | **60** |

**A 90% reduction, with zero variance across three runs each, and both figures equal the oracle's
predicted rates.**

## Why the mechanism holds

The unfixed handler assigns its state on every `timeUpdate`:

```ts
avPlayer.on('timeUpdate', (time: number) => {
  this.currentValue = time
})
```

The fix inserts a same-second guard:

```ts
const second: number = Math.floor(time / 1000)
if (second !== this.lastReportedSecond) {
  this.lastReportedSecond = second
  this.currentValue = time
}
```

`timeUpdate` fires about every 100ms, so a minute holds ~600 callbacks; the guard admits one per
distinct second, i.e. ~60. The measured 600 and 60 are exactly those counts.

This is the **same guard shape** as `cloudmusic_play_time_high_frequency_update`, which this
repository measured earlier at 600 vs 60 writes. The approach transferred unchanged: expose the
variant's own condition as a callable, drive it over the ticks a minute of playback produces, and
commit each admitted second.

**Committing the admitted second is essential.** Without it the guarded variant would compare every
tick against its initial value, admit all 600, and the two variants would be indistinguishable - a
trap this repository already hit on the cloudmusic sibling.

## What is measured, and what is not

The collected quantity is the page's state-update count for a minute of ticks, which is what the
oracle names ("count of page state updates / render passes attributable to currentValue during 60s
idle playback"). `timeUpdate` cannot be synthesised by a bench and a real minute of playback would
dominate a run, so the guard is driven directly, as on the cloudmusic sibling. The real state
assignment is instrumented too, so genuine playback would also be counted.

Not collected: the oracle's "plus UI-thread CPU time".

## Instrumentation notes

The host's harness bench drives this case. Adding a second `EntryAbility.onNewWant` was a compile
error ("Duplicate function implementation"), because ytmusic's own instrumenter already installs one -
so the measurement lives **inside that bench**, dispatching on case name, which is the shape the
harness was built for. The bench delegates to `ohmRunPlayerUpdateBench` so the logic stays with the
counter it uses.

`tools/instrument_player_updates.py` also invokes the host instrumenter first, so a single command
prepares the host rather than requiring two in the right order.

## Reproduce

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:updatesPerMinute bash device-tests/run_declared_metric.sh \
  ytmusic_current_playing_timeupdate ytmusic c4b1879 e175817 \
  self-installing:tools/instrument_player_updates.py 3
```
