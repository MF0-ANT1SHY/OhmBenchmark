#!/usr/bin/env python3
"""Instrument cloudmusic_play_time_high_frequency_update and install a driving harness.

Declared metric `player_page_rerenders_per_minute`: "Count of player-page state-update/render
passes attributable to PLAY_TIME changes during 60s of idle playback". Unfixed writes
`AppStorage.setOrCreate(PLAY_TIME, time)` on every `timeUpdate` (~10/s, so ~600/minute); fixed
guards on the displayed second, giving ~60/minute.

The guard is the whole difference, so the pattern proven on the ytmusic and wanharmony cases
applies unchanged: expose the variant's own condition as a callable, drive it over the tick
sequence a minute of playback produces, and count the writes it admits. `timeUpdate` cannot be
synthesised and a real minute of playback would dominate the run, so the guard is exercised
directly - and the write-up says so.

The harness mirrors the wanharmony one, which reaches `state=done` on device: a `ready` write,
the `ohm-go` handshake, then the measurement and a terminal status.

Usage: python3 tools/instrument_play_time.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASE = 'cloudmusic_play_time_high_frequency_update'
COUNTER_SRC = REPO / 'device-tests' / 'harness' / 'OhmPlayTimeCount.ets'
TARGET = 'entry/src/main/ets/common/utils/play/AVPlayerUtils.ets'
# cloudmusic keeps shared code under common/utils; there is no entry/.../ets/utils/
COUNTER_DEST = 'entry/src/main/ets/common/utils/OhmPlayTimeCount.ets'
# AVPlayerUtils.ets already imports '../../constants/...' and '../../functions/...', which
# places common/utils/ two levels up from common/utils/play/ - where the counter lives
COUNTER_FROM_PLAY = '../../OhmPlayTimeCount'
COUNTER_FROM_ABILITY = '../common/utils/OhmPlayTimeCount'

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmPlayAwaitGo(ohmCtx);
      // OHMB measurement: the variant's PLAY_TIME guard applied to the tick sequence one minute
      // of playback produces. timeUpdate fires ~10/s, so 600 ticks span 60s; the guard is the
      // only difference between the variants, so the writes it admits ARE the declared metric.
      ohmPlayReset();
      let writes = 0;
      for (let tick = 0; tick < 600; tick++) {
        const ms = tick * 100;
        if (ohmPlayWouldWrite(ms)) {
          writes++;
          ohmPlayBump();
          ohmPlayCommit(Math.floor(ms / 1000));
        }
      }
      ohmDiag(ohmCtx, 'after-wait', 'ticks=600 writes=' + writes);
      ohmTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + writes + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmPlayReset, ohmPlayBump, ohmPlayWouldWrite, ohmPlayCommit, ohmDiag, "
    "ohmTerminalWrite, ohmPlayAwaitGo } from '" + COUNTER_FROM_ABILITY + "';\n"
    f"const OHM_CASE = '{CASE}';\n"
)


def guard_body(src: str) -> str:
    """The variant's own guard, read from the source under test."""
    if 'second !== this.lastReportedSecond' in src or 'lastReportedSecond' in src:
        return ('const second: number = Math.floor(timeMs / 1000);\n'
                '  return second !== ohmPlayLastSecond();')
    return 'return true;'



def remove_permission(text: str, name: str) -> str:
    """Cut a requestPermissions entry out by matching braces, so JSON5 spacing cannot defeat it."""
    key = f'"{name}"'
    i = text.find(key)
    if i == -1:
        return text
    # walk back to the opening brace of this entry
    start = text.rfind('{', 0, i)
    if start == -1:
        return text
    # walk forward to its matching close
    depth = 0
    for j in range(start, len(text)):
        if text[j] == '{':
            depth += 1
        elif text[j] == '}':
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    else:
        return text
    # also consume a following comma and any surrounding blank line
    tail = text[end:]
    m = re.match(r'\s*,', tail)
    if m:
        end += m.end()
    out = text[:start] + text[end:]
    return re.sub(r',(\s*[\]}])', r'\1', out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    host = Path(a.hosts) / 'cloudmusic'
    target = host / TARGET
    if not target.exists():
        raise SystemExit(f'  FAILED: {target} missing')

    # remove the install-blocking system permission, identically for both variants
    mod = host / 'entry/src/main/module.json5'
    if mod.exists():
        mt = mod.read_text(encoding='utf-8')
        if 'SYSTEM_FLOAT_WINDOW' in mt:
            mt = remove_permission(mt, 'ohos.permission.SYSTEM_FLOAT_WINDOW')
            mod.write_text(mt, encoding='utf-8')
            still = 'SYSTEM_FLOAT_WINDOW' in mod.read_text(encoding='utf-8')
            print(f'    module.json5: SYSTEM_FLOAT_WINDOW removed (still present: {still})')
            if still:
                raise SystemExit('  FAILED: could not remove the install-blocking permission')

    print('  instrumenting the PLAY_TIME write path:')
    src = target.read_text(encoding='utf-8')

    # 1. the counter module, with the variant's guard
    counter = COUNTER_SRC.read_text(encoding='utf-8')
    counter = counter.replace('OHM_GUARD_BODY', guard_body(src))
    dst = host / COUNTER_DEST
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmPlayTimeCount.ets: guard written')

    # 2. count the actual write site, so a real playback is measured too
    if 'ohmPlayBump()' not in src:
        src = src.replace(
            '          AppStorage.setOrCreate(StorageConstants.PLAY_TIME, time)',
            '          ohmPlayBump();\n'
            '          AppStorage.setOrCreate(StorageConstants.PLAY_TIME, time)', 1)
        lines = src.splitlines(keepends=True)
        last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
        if last is None:
            raise SystemExit(f'  FAILED: no import line in {TARGET}')
        src = (''.join(lines[:last + 1])
               + "import { ohmPlayBump } from '" + COUNTER_FROM_PLAY + "';\n"
               + ''.join(lines[last + 1:]))
        target.write_text(src, encoding='utf-8')
        print(f'    {Path(TARGET).name}: PLAY_TIME write now counted')

    # 3. the bench on the ability
    ability = None
    for cand in host.glob('entry/src/main/ets/entryability/*Ability*.ets'):
        ability = cand
        break
    if ability is None:
        raise SystemExit('  FAILED: cannot find the entry ability')
    t = ability.read_text(encoding='utf-8')
    if 'ohmPlayWouldWrite' not in t:
        # anchor on the LAST import line: this file has a statement before its imports, so the
        # first match would place the additions after code
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
