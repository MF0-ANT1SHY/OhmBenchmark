#!/usr/bin/env python3
"""Install the wanharmony progress-log harness and instrument the case.

Does all three pieces itself, so there is no patch with hunk counts to get wrong:

  1. writes `OhmLogCount.ets` (counter, variant guard, diag and terminal writers);
  2. adds the bench to `EntryAbility.onNewWant`, which is how this host already triggers benches -
     it drives the guard over the progress sequence a page load produces and writes the terminal
     status, so no page, no Web component and no fixture are involved;
  3. instruments `LogUtils.log()` and the `onProgressChange` handler, keeping each variant's own
     body.

The guard body written in step 1 is chosen from the source actually checked out, so it matches the
variant under test.

Idempotent. Usage: python3 tools/instrument_progress_log.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASE_NAME = 'wanharmony_web_progress_log_storm'
COUNTER_SRC = REPO / 'device-tests' / 'harness' / 'OhmLogCount.ets'

BENCH = '''
  onNewWant(want: Want): void {
    if (want.parameters && want.parameters['bench']) {
      // OHMB measurement: the variant's progress-log guard applied to the sequence a page load
      // produces. The guard is the only difference between the variants, so the count of events
      // it admits IS the declared log_calls_per_pageload.
      ohmProgressLogReset();
      let wouldLog = 0;
      for (let p = 0; p <= 100; p++) {
        if (ohmProgressLogWouldLog(p)) {
          wouldLog++;
          ohmProgressLogBump();
        }
      }
      const ohmCtx = this.context as common.UIAbilityContext;
      ohmDiag(ohmCtx, 'after-wait', 'progressValues=101 wouldLog=' + wouldLog);
      ohmTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + wouldLog + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmProgressLogReset, ohmProgressLogBump, ohmProgressLogWouldLog, ohmDiag, "
    "ohmTerminalWrite } from '../utils/OhmLogCount';\n"
    f"const OHM_CASE = '{CASE_NAME}';\n"
)


def guard_body(page_text: str) -> str:
    """The variant's own guard condition, taken from the source under test."""
    if 'event.newProgress % 25 === 0' in page_text:
        return 'return progress === 100 || progress % 25 === 0;'
    return 'return true;'


def write_counter(host: Path, body: str) -> None:
    src = COUNTER_SRC.read_text(encoding='utf-8').replace('OHM_GUARD_BODY', body)
    dst = host / 'entry/src/main/ets/utils/OhmLogCount.ets'
    dst.write_text(src, encoding='utf-8')
    print(f'    OhmLogCount.ets: guard = {body}')


def instrument_log(host: Path) -> None:
    p = host / 'entry/src/main/ets/utils/LogUtils.ets'
    t = p.read_text(encoding='utf-8')
    if 'ohmLogCount' not in t:
        t = t.replace(
            'let domain = 0',
            'let domain = 0\n\n'
            '// OHMB log counter (measurement only)\n'
            'export let ohmLogCount: number = 0;\n'
            'export function ohmLogReset(): void { ohmLogCount = 0; }\n'
            'export function ohmLogTotal(): number { return ohmLogCount; }', 1)
        t = t.replace(
            'export function log(message: string, tag: string = TAG) {\n  if (!showLog) {\n    return\n  }',
            'export function log(message: string, tag: string = TAG) {\n'
            '  if (!showLog) {\n    return\n  }\n  ohmLogCount++;', 1)
        p.write_text(t, encoding='utf-8')
    print('    LogUtils.ets: log() counts every invocation')


def instrument_handler(host: Path) -> str:
    p = host / 'entry/src/main/ets/pages/WebPage.ets'
    t = p.read_text(encoding='utf-8')
    if 'ohmProgressLogBump' not in t:
        guarded = 'if (event.newProgress === 100 || event.newProgress % 25 === 0) {' in t
        if guarded:
            t = t.replace(
                '              log(`onProgressChange progress: ${event.newProgress}`, "WebPage")',
                '              ohmProgressLogBump();\n'
                '              log(`onProgressChange progress: ${event.newProgress}`, "WebPage")', 1)
        else:
            t = t.replace(
                '            log(`onProgressChange progress: ${event.newProgress}`, "WebPage")',
                '            ohmProgressLogBump();\n'
                '            log(`onProgressChange progress: ${event.newProgress}`, "WebPage")', 1)
        t = re.sub(r"^(import .*\n)", r"\1import { ohmProgressLogBump } from '../utils/OhmLogCount';\n",
                   t, count=1, flags=re.M)
        p.write_text(t, encoding='utf-8')
    return guard_body(t)


def install_bench(host: Path) -> None:
    p = host / 'entry/src/main/ets/entryability/EntryAbility.ets'
    t = p.read_text(encoding='utf-8')
    if 'ohmProgressLogWouldLog' in t:
        print('    EntryAbility.ets: bench already installed')
        return
    anchor = "import { log } from '../utils/LogUtils';"
    if t.count(anchor) != 1:
        # fall back to the first import line, which is unique in practice
        import re as _re
        m = _re.search(r'^(import .*\n)', t, _re.M)
        if not m:
            raise SystemExit('  FAILED: no import line to anchor the bench imports to')
        t = t[:m.end()] + IMPORTS + t[m.end():]
    else:
        t = t.replace(anchor, anchor + "\n" + IMPORTS, 1)
    m = re.search(r'(export default class EntryAbility extends UIAbility \{\n)', t)
    if not m:
        raise SystemExit('  FAILED: cannot find the ability class')
    t = t[:m.end()] + BENCH + t[m.end():]
    p.write_text(t, encoding='utf-8')
    print('    EntryAbility.ets: bench installed on onNewWant')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    host = Path(a.hosts) / 'wanharmony'
    page = host / 'entry/src/main/ets/pages/WebPage.ets'
    if not page.exists():
        raise SystemExit(f'  FAILED: {page} missing')
    print('  installing the wanharmony progress-log harness:')
    body = instrument_handler(host)
    write_counter(host, body)
    instrument_log(host)
    install_bench(host)
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
