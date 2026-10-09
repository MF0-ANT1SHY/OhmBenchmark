#!/usr/bin/env python3
"""Count preference flush operations for interviewapp_search_history_sync_flush.

The case declares `flush_count_per_search_burst`: how many preference flush (disk write)
operations the history store performs during a search burst. The oracle states
"unfixed: 10 flushes (one per search); fixed: 1 flush after the burst".

The harness actually drives **1000** `setItem` calls per burst, and unfixed `setItem` calls
`this.store.flush()` on every one, so the expected unfixed count is 1000 rather than 10 - the
oracle's number is written for a 10-search burst this fixture does not use. The fixed build
debounces with a 2s timer, so it should flush once.

The counter routes the store's flush calls through a counting wrapper and emits the tally as
`OHMB/FlushCount`. Idempotent, and it verifies it reached the expected sites.

Usage: python3 tools/instrument_flush_count.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARK = '// OHMB flush counter (measurement only)'
HELPER = (
    f'  {MARK}\n'
    '  private ohmFlush(): void {\n'
    '    ohmFlushCount++\n'
    '    this.store.flush()\n'
    '  }\n\n'
)
# module-level, exported: HistoryStore itself is not exported from history.ets, so the bench
# cannot read a class static; it imports this getter instead.
ACCESSOR = (
    f'\n{MARK}\n'
    'export let ohmFlushCount: number = 0\n'
    f'{MARK}\n'
    'export function resetOhmFlushCount(): void {\n'
    '  ohmFlushCount = 0\n'
    '}\n'
    f'{MARK}\n'
    'export function getOhmFlushCount(): number {\n'
    '  return ohmFlushCount\n'
    '}\n'
)
# `setItem` and `delItem` flush; `clear` does not. The wrapper's own flush is
# excluded, so two is the correct number of call sites to rewrite.
EXPECTED_CALL_SITES = 2


def strip_previous(t: str) -> str:
    # restore the routed call sites first, otherwise a second run finds nothing to rewrite
    t = t.replace('this.ohmFlush()', 'this.store.flush()')
    t = t.replace(HELPER, '')
    t = re.sub(r'[ \t]*// OHMB flush counter \(measurement only\)\n', '', t)
    t = re.sub(r'[ \t]*private ohmFlush\(\): void \{\n'
               r'[ \t]*ohmFlushCount\+\+;\n'
               r'[ \t]*this\.store\.flush\(\)\n'
               r'[ \t]*\}\n\n?', '', t)
    t = re.sub(r'export let ohmFlushCount: number = 0\n', '', t)
    t = re.sub(r'export function resetOhmFlushCount\(\): void \{\n'
               r'[ \t]*ohmFlushCount = 0\n\}\n', '', t)
    t = re.sub(r'export function getOhmFlushCount\(\): number \{\n'
               r'[ \t]*return ohmFlushCount\n\}\n', '', t)
    return t


def instrument_history(path: Path) -> None:
    t = strip_previous(path.read_text(encoding='utf-8'))

    m = re.search(r'(class HistoryStore \{\n)', t)
    if not m:
        raise SystemExit(f'cannot find the class opening in {path}')
    # insert the helper, marking its own flush call so the next step cannot rewrite it
    t = t[:m.end()] + HELPER.replace('this.store.flush()', 'this.store.flush() /* OHMB_HELPER */') + t[m.end():]

    # route the remaining store.flush() calls through the counter
    def repl(mm):
        return 'this.ohmFlush()'
    t, n = re.subn(r'this\.store\.flush\(\)(?!\s*/\* OHMB_HELPER \*/)', repl, t)
    if n != EXPECTED_CALL_SITES:
        raise SystemExit(f'  FAILED: rewrote {n} call site(s), expected {EXPECTED_CALL_SITES}; '
                         f'refusing to leave a half-instrumented tree')

    t = t.replace('this.store.flush() /* OHMB_HELPER */', 'this.store.flush()')
    t = t.rstrip('\n') + '\n' + ACCESSOR
    path.write_text(t, encoding='utf-8')
    print(f'    {path.name}: counting {n} flush call site(s)')


def instrument_bench(path: Path) -> None:
    t = path.read_text(encoding='utf-8')
    if 'HISTORYSTORE_IMPORT' not in t and 'historyStore' in t:
        pass  # the bench already imports the store
    if 'getOhmFlushCount' not in t:
        t = t.replace("import { historyStore } from './history';",
                      "import { historyStore, getOhmFlushCount, resetOhmFlushCount } from './history';", 1)
    if "import hiTraceMeter" not in t:
        m = re.search(r'^(import .*\n)', t, re.M)
        t = t[:m.end()] + "import hiTraceMeter from '@ohos.hiTraceMeter';\n" + t[m.end():]

    # Strip anything a previous run left behind, anywhere in the file.
    t = re.sub(r"[ \t]*hiTraceMeter\.traceByValue\('OHMB/FlushCount'[^\n]*\n", '', t)
    t = re.sub(r"[ \t]*resetOhmFlushCount\(\);\n", '', t)

    # Uniquely identify the search-burst branch: it is the one that waits for the app's own
    # deferred flush, and it is the only place `getAll()` is returned directly.
    burst_loop = "    for (let i=0;i<1000;i++) historyStore.setItem('HarmonyOS interview question '+i);"
    burst_wait = "    await new Promise<void>((resolve) => { setTimeout(resolve, 3000); });"
    if burst_loop not in t or burst_wait not in t:
        raise SystemExit(f'  FAILED: cannot identify the search-burst branch in {path}')

    reset = "    resetOhmFlushCount();\n" + burst_loop
    t = t.replace(burst_loop, reset, 1)
    marker = "    hiTraceMeter.traceByValue('OHMB/FlushCount', getOhmFlushCount());\n"
    t = t.replace(burst_wait, marker + burst_wait, 1)
    path.write_text(t, encoding='utf-8')
    print(f'    {path.name}: reset + OHMB/FlushCount placed in the search-burst branch')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    hosts = Path(a.hosts)
    base = hosts / 'interviewapp' / 'features' / 'home' / 'src' / 'main' / 'ets'
    hist = base / 'utils' / 'history.ets'
    bench = base / 'utils' / 'InterviewBench.ets'
    for p in (hist, bench):
        if not p.exists():
            raise SystemExit(f'  FAILED: missing {p}')
    print('  instrumenting interviewapp host:')
    instrument_history(hist)
    instrument_bench(bench)
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
