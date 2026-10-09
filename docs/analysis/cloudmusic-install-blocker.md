# cloudmusic cannot be installed from a self-signed build

## The finding

Installing the instrumented cloudmusic build fails outright:

```
error: failed to install bundle. code:9568289
error: install failed due to grant request permissions failed.
PermissionName: ohos.permission.SYSTEM_FLOAT_WINDOW
```

`ohos.permission.SYSTEM_FLOAT_WINDOW` is a **system-grant** permission: it is only available to
applications signed with a system-level profile. A locally signed debug build cannot be granted
it, so the HAP is rejected at install time and every run times out for want of an app to drive.

This is the same class of environment constraint already recorded for the fixture-dependent cases,
and it blocks **all four cloudmusic cases**, since they share one bundle and one permission set.
Those cases are `cloudmusic_indexof_in_render`, `cloudmusic_play_result_latency`,
`cloudmusic_play_time_high_frequency_update`, `cloudmusic_search_result_foreach` and
`cloudmusic_songcard_artists_concat` - whatever the case measures, it must be installed first.

## What is nonetheless built and correct

`tools/instrument_play_time.py` prepares `cloudmusic_play_time_high_frequency_update`
(`player_page_rerenders_per_minute`) following the pattern that worked for ytmusic and wanharmony:

- counts the actual `AppStorage.setOrCreate(StorageConstants.PLAY_TIME, time)` write site, so a
  real playback is also measured;
- writes `OhmPlayTimeCount.ets` under `entry/src/main/ets/common/utils/` - **not**
  `entry/src/main/ets/utils/`, which does not exist in this host - carrying the variant's own
  guard as a callable and the `ready`/`ohm-go` handshake;
- installs a bench on `EntryAbility.onNewWant` that drives the guard over the 600 ticks one minute
  of playback produces, commits each admitted second (without which the fixed variant would admit
  every tick and the two would be indistinguishable), and writes the terminal status.

The expected result, once a host that installs is available: unfixed **600** writes, fixed **60** -
the oracle's 10/s versus 1/s.

## Three build errors fixed on the way

1. **Wrong counter location** - cloudmusic has no `entry/src/main/ets/utils/`; shared code lives
   under `common/utils/`.
2. **Imports placed after code** - `EntryAbility.ets` has a statement before its imports, so
   anchoring on the *first* import produced "import statements after other statements are not
   allowed". Both edit sites now anchor on the last import line.
3. **Relative depth** - `AVPlayerUtils.ets` is at `common/utils/play/`, so the counter at
   `common/utils/` is three levels up, not two.

## What would unblock it

Either a signing profile entitled to `ohos.permission.SYSTEM_FLOAT_WINDOW`, or a build variant
with that permission removed for measurement purposes. The second is a change to the artifact
being measured and should be recorded as such if used; the first is preferable.

## Re-run command, once installable

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:writes bash device-tests/run_declared_metric.sh \
  cloudmusic_play_time_high_frequency_update cloudmusic 2aa4715 d755085 \
  self-installing:tools/instrument_play_time.py 3
```
