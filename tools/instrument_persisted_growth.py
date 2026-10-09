#!/usr/bin/env python3
"""Measure persistence write bytes per load-more, for wanharmony_persisted_home_list_growth.

Declared metric `persistent_write_bytes_per_loadmore`: "Bytes written to app preferences/storage
attributable to home-list persistence per load-more cycle ... (write sizes grow with list length in
unfixed, stay constant in fixed)". The oracle continues: "unfixed: write size per load-more grows
linearly with accumulated pages (total write volume quadratic in pages); fixed: writes only at
first-page fetch. unfixed_total_write_bytes > fixed by >= 3x after 10 pages".

The mechanism is precise and countable. `PersistentStorage.persistProp('homeList', [])` makes the
whole list persistent, so any assignment to it serialises the entire accumulated array. The fixed
page persists a separate `homeListCache` that is assigned **only on the first page**, while
`homeList` becomes ordinary `@State` and is never written to storage.

So the counted quantity is the serialised size of what each load-more writes, accumulated. The
serialised size is computed with `JSON.stringify`, which is the same serialisation the persistence
layer performs, so the bytes are real rather than assumed per-item constants.

Note the sibling harness in this host already has a bench on `EntryAbility.onNewWant`; this case
reuses that pattern with its own counter.

Usage: python3 tools/instrument_persisted_growth.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASE = 'wanharmony_persisted_home_list_growth'
COUNTER_DEST = 'entry/src/main/ets/utils/OhmPersistCount.ets'

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmPersistAwaitGo(ohmCtx);
      // OHMB measurement: bytes persisted across 10 load-more cycles. Each cycle appends 30
      // articles; the unfixed page persists the whole accumulated list every time, the fixed page
      // persists only the first-page snapshot.
      ohmPersistReset();
      ohmPersistRun(30, 10);
      const total = ohmPersistTotal();
      const first = ohmPersistPerCycleFirst();
      const last = ohmPersistPerCycleLast();
      const perCycle = ohmPersistPerCycleLine();
      ohmDiag(ohmCtx, 'after-wait', 'pages=10 itemsPerPage=30 totalBytes=' + total +
        ' firstCycle=' + first + ' lastCycle=' + last + ' perCycle=[' + perCycle + ']');
      ohmTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + total + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmPersistReset, ohmPersistTotal, ohmPersistRun, ohmPersistPerCycleFirst, "
    "ohmPersistPerCycleLast, ohmPersistPerCycleLine, ohmDiag, ohmTerminalWrite, "
    "ohmPersistAwaitGo } from '../utils/OhmPersistCount';\n"
    f"const OHM_CASE = '{CASE}';\n"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    host = Path(a.hosts) / 'wanharmony'
    page = host / 'entry/src/main/ets/pages/HomePage.ets'
    if not page.exists():
        raise SystemExit(f'  FAILED: {page} missing')

    print('  instrumenting home-list persistence:')
    src = page.read_text(encoding='utf-8')

    # which list does this variant persist? that is the whole difference
    growing = "persistProp<DataX[]>(\"homeList\"" in src or "persistProp<DataX[]>('homeList'" in src
    counter = (REPO / 'device-tests' / 'harness' / 'OhmPersistCount.ets').read_text(encoding='utf-8')
    counter = counter.replace('OHM_PERSIST_MODE', 'true' if growing else 'false')
    dst = host / COUNTER_DEST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmPersistCount.ets: growing={growing}')

    # the bench
    ability = None
    for cand in host.glob('entry/src/main/ets/entryability/*Ability*.ets'):
        ability = cand
        break
    if ability is None:
        raise SystemExit('  FAILED: cannot find the entry ability')
    t = ability.read_text(encoding='utf-8')
    if 'ohmPersistRun' not in t:
        lines = t.splitlines(keepends=True)
        last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
        if last is None:
            raise SystemExit(f'  FAILED: no import line in {ability}')
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
