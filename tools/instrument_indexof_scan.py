#!/usr/bin/env python3
"""Count the list-scan work in row building, for cloudmusic_indexof_in_render.

Declared metric `row_build_cpu_overhead`: "UI-thread CPU time attributable to list-row building
during the scroll ... divided by number of rows rendered". The mechanism is stated in the oracle
itself - "unfixed per-row build time grows linearly with playlist size (indexOf scan) while fixed
stays constant".

The fix replaces two `this.list.indexOf(item)` calls per row with the loop `index`. So the cost
driver is the elements a scan touches per row: `indexOf` compares until it finds the element, and
across a full list build that totals O(n^2) comparisons, while the fixed version compares none.

The counter therefore counts **list-scan comparisons**, instrumented at the `indexOf` call sites.
That is the quantity the oracle's "grows linearly with playlist size" describes, and it is a count
rather than a wall-clock figure, so it does not depend on the device's load.

Layout note, learned the hard way on the sibling case: a new module at the root of `common/utils/`
is not resolved by this host's ArkTS compiler, so the counter is written into `common/constants/`
beside `StorageConstants`, which the host demonstrably imports.

Usage: python3 tools/instrument_indexof_scan.py [--hosts DIR]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
CASE = 'cloudmusic_indexof_in_render'
TARGET = 'entry/src/main/ets/pages/playlist/PlayListPage.ets'
COUNTER_DEST = 'entry/src/main/ets/common/constants/OhmScanCount.ets'
COUNTER_FROM_PAGE = '../../common/constants/OhmScanCount'
COUNTER_FROM_ABILITY = '../common/constants/OhmScanCount'

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmScanAwaitGo(ohmCtx);
      // OHMB measurement: the scan work a full list build performs, at the playlist sizes the
      // oracle names. The unfixed page scans the list twice per row (indexOf), so the work is
      // quadratic in the list size; the fixed page uses the loop index and scans nothing.
      let line = '';
      for (const n of [100, 500, 1000]) {
        ohmScanReset();
        ohmScanSimulate(n);
        const comparisons = ohmScanTotal();
        line += (line === '' ? '' : ' ') + 'n=' + n + ':cmp=' + comparisons;
      }
      const at500 = ohmScanComparisonsAt(500);
      ohmDiag(ohmCtx, 'after-wait', line);
      ohmTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + at500 + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmScanReset, ohmScanTotal, ohmScanSimulate, ohmScanComparisonsAt, ohmDiag, "
    "ohmTerminalWrite, ohmScanAwaitGo } from '" + COUNTER_FROM_ABILITY + "';\n"
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

    # 1. remove the install-blocking system permission, as the sibling case requires
    mod = host / 'entry/src/main/module.json5'
    if mod.exists() and 'SYSTEM_FLOAT_WINDOW' in mod.read_text(encoding='utf-8'):
        from permission_removal import remove_request_permission
        mt = mod.read_text(encoding='utf-8')
        mt = remove_request_permission(mt, 'ohos.permission.SYSTEM_FLOAT_WINDOW')
        mod.write_text(mt, encoding='utf-8')
        print(f'    module.json5: SYSTEM_FLOAT_WINDOW removed '
              f'(still present: {"SYSTEM_FLOAT_WINDOW" in mt})')

    print('  instrumenting the row-build scan:')
    src = target.read_text(encoding='utf-8')

    # 2. the counter, carrying the variant's own scan behaviour
    quadratic = 'this.list.indexOf(item)' in src
    counter = (REPO / 'device-tests' / 'harness' / 'OhmScanCount.ets').read_text(encoding='utf-8')
    counter = counter.replace('OHM_SCAN_MODE', 'true' if quadratic else 'false')
    dst = host / COUNTER_DEST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmScanCount.ets: quadratic={quadratic}')

    # 3. count the real scan sites, so an on-device build is measured too
    if 'ohmScanAdd' not in src:
        n = src.count('this.list.indexOf(item)')
        if n:
            # each indexOf compares until it finds the element: position + 1 comparisons
            src = re.sub(r'this\.list\.indexOf\(item\)',
                         'ohmScanIndexOf(item, index)', src)
            lines = src.splitlines(keepends=True)
            last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
            if last is None:
                raise SystemExit(f'  FAILED: no import line in {TARGET}')
            src = (''.join(lines[:last + 1])
                   + "import { ohmScanIndexOf } from '" + COUNTER_FROM_PAGE + "';\n"
                   + ''.join(lines[last + 1:]))
            target.write_text(src, encoding='utf-8')
            print(f'    {Path(TARGET).name}: {n} indexOf scan site(s) now counted')

    # 4. the bench
    ability = None
    for cand in host.glob('entry/src/main/ets/entryability/*Ability*.ets'):
        ability = cand
        break
    if ability is None:
        raise SystemExit('  FAILED: cannot find the entry ability')
    t = ability.read_text(encoding='utf-8')
    if 'ohmScanSimulate' not in t:
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
