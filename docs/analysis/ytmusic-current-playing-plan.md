# ytmusic_current_playing_timeupdate: mechanism, and the exact shape of the driver

## The bug

The unfixed page assigns its state on **every** `timeUpdate` callback:

```ts
avPlayer.on('timeUpdate', (time: number) => {
  this.currentValue = time
})
```

The fixed page only assigns when the displayed second changes:

```ts
avPlayer.on('timeUpdate', (time: number) => {
  const second: number = Math.floor(time / 1000)
  if (second !== this.lastReportedSecond) {
    this.lastReportedSecond = second
    this.currentValue = time
  }
})
```

Declared metric `player_page_updates_per_minute`, oracle "unfixed ~600/minute vs fixed
~60/minute". Those figures are consistent with a real player emitting `timeUpdate` about every
100ms: 600 callbacks per minute, of which a same-second guard passes about 60.

## The key finding for driving it

`setAVPlayerCallback` is **not** called at component construction - it is called from the
page's `onPageShow`:

```
line  78  async onPageShow(): Promise<void> {
line  86    this.setAVPlayerCallback(this.avplayer)
```

So the route-and-tick approach used for the history case transfers, with one extra requirement:
the page must have a player when it is shown, and that player must be one the bench can tick.

## The driver, in three parts

1. **A stub player, installed before routing.** The bench puts a stub into `AppStorage` under a
   known key, and a small instrumented hook in `onPageShow` prefers it over the real
   `this.avplayer`. The stub needs only what the page touches on the `timeUpdate` path plus
   whatever `onPageShow` calls before `setAVPlayerCallback`; the `media.AVPlayer` interface is
   large, so this hook is what keeps the stub small. Everything else the page does with the
   player (slider bounds, duration) is already null-tolerant in the existing code.
2. **Tick delivery at 100ms spacing**, matching the real callback cadence, over a window of
   about 60 ticks (6s).
3. **The counter on the assignment**, not on the callback. This matters: counting callbacks
   would report 60 for *both* variants, because the callback fires regardless - it is the state
   assignment that the fix removes. The instrumented line is therefore the `this.currentValue =`
   assignment, and the two assignments in the file (the `timeUpdate` one and the `currentValue =
   0` reset) must be distinguished so only the former is counted.

## The per-minute trap

The oracle quotes **per minute**. A 6-second window measures 60 ticks and reports a rate; the
projection to per-minute must be labelled as a projection, not presented as a measured count
over a minute. The document that records the result should state the window explicitly, so the
number is not mistaken for a 60-second observation. Extending the window to a true 60 seconds is
possible but multiplies each run's cost by ten for a ratio that the shorter window already
establishes cleanly.

## Expected result

With 60 ticks spanning 6 seconds (timestamps 0..5900ms, so 6 distinct seconds):

| variant | state assignments | projected per minute |
| --- | --- | --- |
| unfixed | 60 | 600 |
| fixed | 6 | 60 |

which is the oracle's 10:1 ratio. The check that the driver is wired correctly is that the
unfixed count equals the tick count exactly; if it is lower, the stub is not reaching the page.

## Status

- mechanism: **understood and confirmed by reading both sides of the patch**
- driver: **designed, not yet built** - the missing piece is the stub player plus the
  `onPageShow` preference hook
- the harness it needs (`OhmProbe.ets`, `Diag.ets`, `YtMusicBench.ets`) **is already built,
  installs and runs on device** for the history case
