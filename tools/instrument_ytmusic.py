#!/usr/bin/env python3
"""Install the ytmusic measurement harness, which does not exist upstream.

ytmusic is the one host with no `device-tests/patches/ytmusic*/` entry, so the three ytmusic
cases could never be measured: there is no OhmProbe, no bench entry and no hook in
EntryAbility. This writes them, mirroring the harness the other hosts use so the collector and
trace analysis work unchanged:

  entry/src/main/ets/utils/OhmProbe.ets        probe + per-case counters
  entry/src/main/ets/utils/YtMusicBench.ets    bench entry
  EntryAbility.onNewWant                       triggers the bench on a `bench` want parameter

It also instruments the case under test:

  ytmusic_history_json_parse_per_row - counts every JSON.parse the history page performs.
  The instrumented `ohmParse` helper is injected into each file that parses, and call sites
  are rewritten to use it, so the count is exact rather than inferred. Unfixed parses each row
  several times per build; fixed parses once.

Usage: python3 tools/instrument_ytmusic.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARK = '// OHMB json parse counter (measurement only)'

PARSER_HELPER = f'''
{MARK}
export let ohmJsonParseCount: number = 0;
{MARK}
export function ohmParseTotal(): number {{
  return ohmJsonParseCount;
}}
{MARK}
export function ohmParse(text: string): Record<string, string> {{
  ohmJsonParseCount++;
  return JSON.parse(text) as Record<string, string>;
}}
'''


def install_probe(base: Path) -> None:
    """Copy the probe and bench entry into the host."""
    utils = base / 'utils'
    utils.mkdir(parents=True, exist_ok=True)
    for name, src in (('OhmProbe.ets', REPO / 'device-tests' / 'harness' / 'OhmProbe.ets'),
                      ('Diag.ets', REPO / 'device-tests' / 'harness' / 'Diag.ets'),
                      ('YtMusicBench.ets', REPO / 'device-tests' / 'harness' / 'YtMusicBench.ets')):
        dst = utils / name
        if not src.exists():
            raise SystemExit(f'  FAILED: missing harness template {src}')
        dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
        print(f'    wrote {dst.relative_to(base.parents[3])}' if len(base.parents) > 3
              else f'    wrote {dst}')


def hook_entry_ability(base: Path, case: str) -> None:
    p = base / 'entryability' / 'EntryAbility.ets'
    t = p.read_text(encoding='utf-8')
    if 'runYtMusicBench' in t:
        print(f'    {p.name}: already hooked')
        return
    if "import { runYtMusicBench }" not in t:
        m = re.search(r'^(import .*\n)', t, re.M)
        t = t[:m.end()] + "import { runYtMusicBench } from '../utils/YtMusicBench';\n" + t[m.end():]
    # add or extend onNewWant
    if 'onNewWant(' in t:
        m = re.search(r'onNewWant\([^)]*\)[^{]*\{', t)
        t = t[:m.end()] + ("\n    if (want.parameters && want.parameters['bench']) {\n"
                           "      runYtMusicBench(this.context, want.parameters['bench'].toString());\n"
                           "    }\n") + t[m.end():]
    else:
        m = re.search(r'(export default class \w+ extends UIAbility \{\n)', t)
        if not m:
            raise SystemExit(f'  FAILED: cannot find the ability class in {p}')
        t = t[:m.end()] + ("\n  onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {\n"
                           "    if (want.parameters && want.parameters['bench']) {\n"
                           "      runYtMusicBench(this.context, want.parameters['bench'].toString());\n"
                           "    }\n  }\n") + t[m.end():]
        if 'Want' not in t.split('\n')[0] and 'Want,' not in t:
            t = t.replace("import UIAbility", "import { Want } from '@kit.AbilityKit';\nimport UIAbility", 1)
    p.write_text(t, encoding='utf-8')
    print(f'    {p.name}: bench hook added')


def instrument_json_parse(base: Path) -> None:
    """Rewrite JSON.parse call sites to a counting helper, per file that parses."""
    targets = [base / 'pages' / 'History.ets', base / 'pages' / 'CurrentPlaying.ets',
               base / 'pages' / 'SearchPage.ets']
    total = 0
    for p in targets:
        if not p.exists():
            print(f'    {p.name}: not present, skipped')
            continue
        t = p.read_text(encoding='utf-8')
        if MARK in t:
            print(f'    {p.name}: already instrumented')
            continue
        t, n = re.subn(r'(?<![\w.])JSON\.parse\(', 'ohmParse(', t)
        if n == 0:
            print(f'    {p.name}: no JSON.parse call sites')
            continue
        # JSON.stringify must stay intact; the regex above cannot match it
        if 'ohmParse' in t and 'function ohmParse' not in t:
            t = t.rstrip('\n') + '\n' + PARSER_HELPER
        p.write_text(t, encoding='utf-8')
        print(f'    {p.name}: {n} JSON.parse call site(s) routed through ohmParse')
        total += n
    if total == 0:
        raise SystemExit('  FAILED: nothing instrumented; refusing to leave a misleading tree')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    base = Path(a.hosts) / 'ytmusic' / 'entry' / 'src' / 'main' / 'ets'
    if not base.exists():
        raise SystemExit(f'  FAILED: {base} not found')
    print('  installing the ytmusic harness:')
    install_probe(base)
    hook_entry_ability(base, 'ytmusic')
    print('  instrumenting the case under test:')
    instrument_json_parse(base)
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
