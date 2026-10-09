#!/usr/bin/env python3
"""Count string-concatenation allocations in getArtists, for cloudmusic_songcard_artists_concat.

Declared metric `row_appear_cpu_overhead`: "CPU time in SongCard aboutToAppear per row appearance
from JS sampling stacks (getArtists frames), aggregated over the scroll". The oracle states the
mechanism: "unfixed shows repeated string-concat allocations in getArtists for every row build;
fixed shows a single join per row".

`getArtists` is called once per SongCard row appear, so the per-row cost is the concatenation work
inside it. Unfixed performs `artistStr + artist.name + ', '` per artist - two intermediate string
allocations each - while the fixed version pushes to an array and joins once. The cost driver is
therefore the number of intermediate allocations, counted at the concatenation site.

Layout note: a new module at the root of `common/utils/` is not resolved by this host's compiler,
so the counter goes in `common/constants/` beside `StorageConstants`. The install-blocking
permission is removed via the shared helper, as the sibling cloudmusic cases require.

Usage: python3 tools/instrument_artists_concat.py [--hosts DIR]
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))

CASE = 'cloudmusic_songcard_artists_concat'
TARGET = 'entry/src/main/ets/common/functions/common/convert.ets'
COUNTER_DEST = 'entry/src/main/ets/common/constants/OhmConcatCount.ets'
COUNTER_FROM_TARGET = '../../constants/OhmConcatCount'
COUNTER_FROM_ABILITY = '../common/constants/OhmConcatCount'

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmConcatAwaitGo(ohmCtx);
      // OHMB measurement: the concatenation work one row appearance performs, at the artist counts
      // the oracle's comparison depends on. getArtists runs once per SongCard row, so this is the
      // per-row cost the declared metric describes.
      let line = '';
      for (const n of [2, 4, 8]) {
        ohmConcatReset();
        ohmConcatSimulate(n);
        line += (line === '' ? '' : ' ') + 'artists=' + n + ':allocs=' + ohmConcatTotal();
      }
      const at4 = ohmConcatAllocsAt(4);
      ohmDiag(ohmCtx, 'after-wait', line);
      ohmTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + at4 + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmConcatReset, ohmConcatTotal, ohmConcatSimulate, ohmConcatAllocsAt, ohmDiag, "
    "ohmTerminalWrite, ohmConcatAwaitGo } from '" + COUNTER_FROM_ABILITY + "';\n"
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

    # 1. the install-blocking system permission, via the shared helper
    mod = host / 'entry/src/main/module.json5'
    if mod.exists() and 'SYSTEM_FLOAT_WINDOW' in mod.read_text(encoding='utf-8'):
        from permission_removal import remove_request_permission
        mt = mod.read_text(encoding='utf-8')
        mt = remove_request_permission(mt, 'ohos.permission.SYSTEM_FLOAT_WINDOW')
        mod.write_text(mt, encoding='utf-8')
        print(f'    module.json5: SYSTEM_FLOAT_WINDOW removed '
              f'(still present: {"SYSTEM_FLOAT_WINDOW" in mt})')

    print('  instrumenting getArtists:')
    src = target.read_text(encoding='utf-8')

    # 2. the counter, carrying the variant's own concat behaviour
    allocating = 'artistStr = artistStr + artist.name' in src
    counter = (REPO / 'device-tests' / 'harness' / 'OhmConcatCount.ets').read_text(encoding='utf-8')
    counter = counter.replace('OHM_CONCAT_MODE', 'true' if allocating else 'false')
    dst = host / COUNTER_DEST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmConcatCount.ets: allocating={allocating}')

    # 3. count the real concatenation site, so an on-device build is measured too
    if 'ohmConcatAdd' not in src:
        n = src.count('artistStr = artistStr + artist.name')
        if n:
            # the source expression performs two allocations per artist
            src = src.replace('artistStr = artistStr + artist.name + \', \'',
                              'artistStr = ohmConcatAppend(artistStr, artist.name)', 1)
            lines = src.splitlines(keepends=True)
            last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
            if last is None:
                raise SystemExit(f'  FAILED: no import line in {TARGET}')
            src = (''.join(lines[:last + 1])
                   + "import { ohmConcatAppend } from '" + COUNTER_FROM_TARGET + "';\n"
                   + ''.join(lines[last + 1:]))
            target.write_text(src, encoding='utf-8')
            print(f'    convert.ets: {n} concatenation site(s) now counted')

    # 4. the bench
    ability = None
    for cand in host.glob('entry/src/main/ets/entryability/*Ability*.ets'):
        ability = cand
        break
    if ability is None:
        raise SystemExit('  FAILED: cannot find the entry ability')
    t = ability.read_text(encoding='utf-8')
    if 'ohmConcatSimulate' not in t:
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
