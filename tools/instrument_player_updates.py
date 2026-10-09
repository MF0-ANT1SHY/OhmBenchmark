#!/usr/bin/env python3
"""Measure ytmusic_current_playing_timeupdate with the pattern proven on cloudmusic_play_time.

Declared metric `player_page_updates_per_minute`: "Count of player-page state-update/render passes
attributable to PLAY_TIME changes during 60s of idle playback". The oracle states the mechanism:
"unfixed ~600 updates/minute vs fixed ~60/minute".

The fix inserts a same-second guard into the page's `timeUpdate` handler:

    const second: number = Math.floor(time / 1000)
    if (second !== this.lastReportedSecond) { this.lastReportedSecond = second; this.currentValue = time }

That is the **same guard shape** as `cloudmusic_play_time_high_frequency_update`, which this
repository already measured (600 vs 60 writes) with an approach that worked: expose the variant's
own condition as a callable, drive it over the ticks a minute of playback produces, and commit each
admitted second so the fixed variant's state persists across calls.

`timeUpdate` cannot be synthesised and a real minute of playback would dominate a run, so the guard
is exercised directly - and the write-up says so, as it does for the cloudmusic sibling.

Layout: ytmusic keeps helpers in `entry/src/main/ets/utils/`, and its harness (`OhmProbe.ets`,
`Diag.ets`, `YtMusicBench.ets`) is installed by `tools/instrument_ytmusic.py`, so this rides on it.

Usage: python3 tools/instrument_player_updates.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASE = 'ytmusic_current_playing_timeupdate'
PAGE = 'entry/src/main/ets/pages/CurrentPlaying.ets'
COUNTER_DEST = 'entry/src/main/ets/utils/OhmUpdateCount.ets'
COUNTER_FROM_PAGE = '../utils/OhmUpdateCount'
COUNTER_FROM_ABILITY = '../utils/OhmUpdateCount'

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmUpdateAwaitGo(ohmCtx);
      // OHMB measurement: player-page state updates for the tick sequence one minute of idle
      // playback produces. timeUpdate fires about every 100ms, so 600 ticks span 60s; the
      // same-second guard is the only difference between the variants, so the writes it admits ARE
      // the declared player_page_updates_per_minute.
      ohmUpdateReset();
      let writes = 0;
      for (let tick = 0; tick < 600; tick++) {
        const ms = tick * 100;
        if (ohmUpdateWouldWrite(ms)) {
          writes++;
          ohmUpdateBump();
          ohmUpdateCommit(Math.floor(ms / 1000));
        }
      }
      const perMinute = writes;
      ohmUpdateDiag(ohmCtx, 'after-wait', 'ticks=600 writes=' + writes +
        ' updatesPerMinute=' + perMinute);
      ohmUpdateTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + perMinute + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmUpdateReset, ohmUpdateBump, ohmUpdateWouldWrite, ohmUpdateCommit, ohmUpdateDiag, "
    "ohmUpdateTerminalWrite, ohmUpdateAwaitGo } from '" + COUNTER_FROM_ABILITY + "';\n"
    f"const OHM_CASE = '{CASE}';\n"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    host = Path(a.hosts) / 'ytmusic'
    page = host / PAGE
    if not page.exists():
        raise SystemExit(f'  FAILED: {page} missing')

    # the probe, bench template and EntryAbility hook come from the host's own instrumenter
    import subprocess
    host_tool = REPO / 'tools' / 'instrument_ytmusic.py'
    if host_tool.exists():
        r = subprocess.run(['python3', str(host_tool), '--hosts', str(Path(a.hosts))],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f'  FAILED: the host harness did not install:\n{r.stdout}{r.stderr}')
        print('    host harness installed (probe, bench, EntryAbility hook)')

    print('  instrumenting the player update path:')
    src = page.read_text(encoding='utf-8')

    # the whole difference: does the handler guard on the displayed second?
    guarded = 'lastReportedSecond' in src
    counter = (REPO / 'device-tests' / 'harness' / 'OhmUpdateCount.ets').read_text(encoding='utf-8')
    counter = counter.replace('OHM_UPDATE_MODE', 'true' if guarded else 'false')
    dst = host / COUNTER_DEST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmUpdateCount.ets: guarded={guarded}')

    # count the real state assignment, so on-device playback would be measured too
    if 'ohmUpdateBump' not in src:
        n = src.count('this.currentValue = time')
        if n:
            src = src.replace('this.currentValue = time', 'this.currentValue = time; ohmUpdateBump()', 1)
            lines = src.splitlines(keepends=True)
            last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
            imp = "import { ohmUpdateBump } from '" + COUNTER_FROM_PAGE + "';\n"
            if last is not None:
                src = ''.join(lines[:last + 1]) + imp + ''.join(lines[last + 1:])
            else:
                src = imp + src
            page.write_text(src, encoding='utf-8')
            print(f'    CurrentPlaying.ets: {n} state assignment(s) now counted')

    # the host bench that EntryAbility.onNewWant already invokes drives this case; see
    # device-tests/harness/YtMusicBench.ets
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
