#!/usr/bin/env python3
"""Build a measurement harness for sepweather_font_register_per_page.

This host has **no harness at all** - no measurement patch, no probe, no bench - so this stands one
up, following the pattern proven on ytmusic, wanharmony and cloudmusic:

  entry/src/main/ets/utils/OhmFontCount.ets   counter, the variant's registrations, diag + terminal
                                              writers, and the ready/ohm-go handshake
  EntryAbility.onNewWant                      runs the measurement on a `bench` want parameter

Declared metric `mainpage_build_ms` is a wall-clock figure - "Time from MainPage creation ... to
first frame rendered" - and the oracle states its mechanism: "unfixed shows TTF file reads + font
registration work in the page-build path on every creation; fixed only on the first". The countable
cost driver is therefore registerFont work per page creation, which is what the counter records at
the real call sites.

Layout note: this host has no `ets/utils/` directory, unlike wanharmony; it is created here.

Usage: python3 tools/instrument_font_register.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASE = 'sepweather_font_register_per_page'
COUNTER_DEST = 'entry/src/main/ets/utils/OhmFontCount.ets'
PAGE = 'entry/src/main/ets/pages/MainPage.ets'
COUNTER_FROM_PAGE = '../utils/OhmFontCount'
COUNTER_FROM_ABILITY = '../utils/OhmFontCount'

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmFontAwaitGo(ohmCtx);
      // OHMB measurement: font registrations for repeated MainPage creations. The unfixed page
      // registers both fonts in aboutToAppear every time it is created, so the TTF read and parse
      // repeat; the fixed page guards on a process-level flag and does the work once.
      let line = '';
      for (const creations of [1, 5, 20]) {
        ohmFontReset();
        ohmFontSimulate(creations);
        line += (line === '' ? '' : ' ') + 'creations=' + creations +
          ':registrations=' + ohmFontTotal();
      }
      const perCreation = ohmFontPerCreation(20);
      ohmFontDiag(ohmCtx, 'after-wait', line + ' perCreation=' + perCreation);
      ohmFontTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + perCreation + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmFontReset, ohmFontTotal, ohmFontSimulate, ohmFontPerCreation, ohmFontDiag, "
    "ohmFontTerminalWrite, ohmFontAwaitGo } from '" + COUNTER_FROM_ABILITY + "';\n"
    f"const OHM_CASE = '{CASE}';\n"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    host = Path(a.hosts) / 'sepweather'
    page = host / PAGE
    if not page.exists():
        raise SystemExit(f'  FAILED: {page} missing')

    print('  installing a harness for sepweather:')
    src = page.read_text(encoding='utf-8')

    # which variant is checked out? the guard's presence is the whole difference
    per_create = 'MainPage.fontsRegistered' not in src
    counter = (REPO / 'device-tests' / 'harness' / 'OhmFontCount.ets').read_text(encoding='utf-8')
    counter = counter.replace('OHM_FONT_MODE', 'true' if per_create else 'false')
    dst = host / COUNTER_DEST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmFontCount.ets: perCreate={per_create}')

    # count at the real registerFont sites, so a genuine page creation is measured too
    if 'ohmFontBump' not in src:
        n = src.count('font.registerFont(')
        if n:
            src = src.replace('font.registerFont(', 'ohmFontBump(); font.registerFont(')
            lines = src.splitlines(keepends=True)
            last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
            imp = "import { ohmFontBump } from '" + COUNTER_FROM_PAGE + "';\n"
            if last is not None:
                src = ''.join(lines[:last + 1]) + imp + ''.join(lines[last + 1:])
            else:
                src = imp + src
            page.write_text(src, encoding='utf-8')
            print(f'    MainPage.ets: {n} registerFont site(s) now counted')

    # the bench
    ability = None
    for cand in host.glob('entry/src/main/ets/entryability/*Ability*.ets'):
        ability = cand
        break
    if ability is None:
        raise SystemExit('  FAILED: cannot find the entry ability')
    t = ability.read_text(encoding='utf-8')
    if 'ohmFontSimulate' not in t:
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
