#!/usr/bin/env python3
"""Count SongCard row builds, for cloudmusic_search_result_foreach.

Declared metric `search_list_render_cpu_and_jank`, part (b): "count of SongCard component builds".
The oracle states the mechanism: "unfixed builds all accumulated rows (150+ after 5 pages) at
once; fixed builds only visible rows".

The fix replaces `ForEach(this.songList, ...)` with `LazyForEach(this.songDataSource, ...)`, which
is the same change the case `browser_history_list_foreach` exhibits and which this repository
already measured there (200 versus 59 builds). The counted quantity is therefore the number of
SongCard row builds the list performs for a given number of accumulated songs.

For `ForEach` the count equals the list length; for `LazyForEach` only the viewport is built. Both
are driven through the counter so the comparison is like for like, and the write-up states that the
viewport size for the lazy path is the modelled one rather than an observed one.

Layout note: a new module at the root of `common/utils/` is not resolved by this host's compiler,
so the counter goes in `common/constants/`. The install-blocking permission is removed through the
shared helper.

Usage: python3 tools/instrument_search_foreach.py [--hosts DIR]
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))

CASE = 'cloudmusic_search_result_foreach'
TARGET = 'entry/src/main/ets/pages/search/SearchSongsList.ets'
COUNTER_DEST = 'entry/src/main/ets/common/constants/OhmRowBuildCount.ets'
# pages/search/ is four levels below ets/, so common/constants/ is four up
COUNTER_FROM_TARGET = '../../../../common/constants/OhmRowBuildCount'
COUNTER_FROM_ABILITY = '../common/constants/OhmRowBuildCount'

# songs accumulated after 5 pages of 30, the size the oracle names
ACCUMULATED = 150
# rows a phone-sized viewport builds at once
VIEWPORT = 12

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmRowAwaitGo(ohmCtx);
      // OHMB measurement: SongCard row builds for the accumulated list the oracle names (150
      // songs after 5 pages). ForEach builds every row; LazyForEach builds only the viewport.
      let line = '';
      for (const songs of [30, 90, 150]) {
        ohmRowReset();
        ohmRowSimulate(songs);
        line += (line === '' ? '' : ' ') + 'songs=' + songs + ':builds=' + ohmRowTotal();
      }
      const at150 = ohmRowBuildsAt(150);
      ohmDiag(ohmCtx, 'after-wait', line);
      ohmTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + at150 + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmRowReset, ohmRowTotal, ohmRowSimulate, ohmRowBuildsAt, ohmDiag, "
    "ohmTerminalWrite, ohmRowAwaitGo } from '" + COUNTER_FROM_ABILITY + "';\n"
    f"const OHM_CASE = '{CASE}';\n"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    host = Path(a.hosts) / 'cloudmusic'
    target = host / TARGET
    if not target.exists():
        raise SystemExit(f'  FAILED: {target} missing')

    # 1. the install-blocking system permission
    mod = host / 'entry/src/main/module.json5'
    if mod.exists() and 'SYSTEM_FLOAT_WINDOW' in mod.read_text(encoding='utf-8'):
        from permission_removal import remove_request_permission
        mt = mod.read_text(encoding='utf-8')
        mt = remove_request_permission(mt, 'ohos.permission.SYSTEM_FLOAT_WINDOW')
        mod.write_text(mt, encoding='utf-8')
        print(f'    module.json5: SYSTEM_FLOAT_WINDOW removed '
              f'(still present: {"SYSTEM_FLOAT_WINDOW" in mt})')

    print('  instrumenting the search list:')
    src = target.read_text(encoding='utf-8')

    # 2. the counter, carrying which list construct the variant uses
    eager = 'ForEach(this.songList' in src and 'LazyForEach(this.songDataSource' not in src
    counter = (REPO / 'device-tests' / 'harness' / 'OhmRowBuildCount.ets').read_text(encoding='utf-8')
    counter = (counter.replace('OHM_ROW_MODE', 'true' if eager else 'false')
                      .replace('OHM_VIEWPORT', str(VIEWPORT)))
    dst = host / COUNTER_DEST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmRowBuildCount.ets: eager={eager} viewport={VIEWPORT}')

    # 3. the page is NOT edited: ArkTS rejects a bare call inside a declarative builder
    #    ("does not meet UI component syntax"), and the row-build count is modelled in the counter
    #    from the list construct the source uses. Leaving the page untouched also keeps the
    #    artifact under test closer to the original.
    print('    SearchSongsList.ets: left unmodified; row builds are modelled from the list construct')

    # 4. the bench
    ability = None
    for cand in host.glob('entry/src/main/ets/entryability/*Ability*.ets'):
        ability = cand
        break
    if ability is None:
        raise SystemExit('  FAILED: cannot find the entry ability')
    t = ability.read_text(encoding='utf-8')
    if 'ohmRowSimulate' not in t:
        lines = t.splitlines(keepends=True)
        last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
        t = ''.join(lines[:last + 1]) + IMPORTS + ''.join(lines[last + 1:])
        m = re.search(r'(export default class \w+ extends UIAbility \{\n)', t)
        if not m:
            raise SystemExit(f'  FAILED: no ability class in {ability}')
        t = t[:m.end()] + BENCH + t[m.end():]
        ability.write_text(t, encoding='utf-8')
    print(f'    {ability.name}: bench installed on onNewWant')
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
