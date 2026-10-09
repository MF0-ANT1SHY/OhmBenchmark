#!/usr/bin/env python3
"""Instrument browser_insert_date_lookup_cache so the harness counts RDB statements per save.

The case declares `rdb_statements_per_page_save`, and its oracle states the shape:

    unfixed: >= 3 statements per page save after the first (SELECT + CREATE TABLE + INSERT)
    fixed:    1 statement per page save (INSERT only)

`RdbUtils.insertDate` runs a date_table SELECT, a conditional INSERT and
`createHistoryTable` (CREATE TABLE IF NOT EXISTS) on every call; the fix adds a
`knownDates` cache so after the first save only the history INSERT remains.

The counter is measurement-only: it prepends an increment and changes no SQL, control flow
or caching, and both variants are instrumented identically. The tally is emitted as an
`OHMB/StatementCount` trace marker, the same mechanism ArticleCardCount / HistoryItemCount
use, so the existing trace analysis can read it.

Idempotent: re-running strips any previous counters first, so a half-instrumented tree
cannot accumulate. It verifies the expected site count and exits non-zero if it cannot
reach it, rather than leaving a tree that fails to compile.

Usage: python3 tools/instrument_statement_count.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARK = '// OHMB statement counter (measurement only)'
FIELD = 'RdbUtils.ohmCount();'
EXPECTED_SITES = 4

COUNTER_BLOCK = (
    f'  {MARK}\n'
    '  static ohmStatements: number = 0\n\n'
    f'  {MARK}\n'
    '  private static ohmCount(n: number = 1): void {\n'
    '    RdbUtils.ohmStatements += n\n'
    '  }\n\n'
)


def strip_previous(t: str) -> str:
    """Remove any earlier instrumentation so this tool is idempotent."""
    t = re.sub(r'[ \t]*// OHMB statement counter \(measurement only\)\n', '', t)
    t = re.sub(r'[ \t]*RdbUtils\.ohmCount\(\);\n', '', t)
    t = re.sub(r'[ \t]*static ohmStatements: number = 0\n\n?', '', t)
    t = re.sub(r'[ \t]*private static ohmCount\([^)]*\): void \{\n'
               r'[ \t]*RdbUtils\.ohmStatements \+= n\n'
               r'[ \t]*\}\n\n?', '', t)
    return t


def instrument_rdb(path: Path) -> None:
    t = strip_previous(path.read_text(encoding='utf-8'))

    m = re.search(r'(export default class RdbUtils \{\n)', t)
    if not m:
        raise SystemExit(f'cannot find the class opening in {path}')
    t = t[:m.end()] + COUNTER_BLOCK + t[m.end():]

    sites = 0

    # 1. the date_table SELECT
    t, n = re.subn(r'(\n[ \t]*)(resultSet = await RdbUtils\.getStore\(\)\.query\()',
                   r'\1RdbUtils.ohmCount();\1\2', t, count=1)
    sites += n

    # 2. the conditional INSERT
    t, n = re.subn(r'(\n[ \t]*)(RdbUtils\.getStore\(\)\.insert\("date_table")',
                   r'\1RdbUtils.ohmCount();\1\2', t, count=1)
    sites += n

    # 3. CREATE TABLE inside createHistoryTable (indentation varies, so do not assume width)
    m = re.search(r'static async createHistoryTable\([^)]*\)\s*\{', t)
    if m:
        end = t.find('\n  }', m.end())
        body = t[m.end():end if end != -1 else len(t)]
        patched, n = re.subn(r'(\n[ \t]*)(await RdbUtils\.executeSql\()',
                             r'\1RdbUtils.ohmCount();\1\2', body, count=1)
        if n:
            t = t[:m.end()] + patched + t[end if end != -1 else len(t):]
            sites += n

    # 4. the history INSERT
    t, n = re.subn(r'(\n[ \t]*)(return RdbUtils\.getStore\(\)\.insert\(tableName)',
                   r'\1RdbUtils.ohmCount();\1\2', t, count=1)
    sites += n

    if sites != EXPECTED_SITES:
        raise SystemExit(f'  FAILED: instrumented {sites} site(s), expected {EXPECTED_SITES}; '
                         f'refusing to leave a half-instrumented tree')
    path.write_text(t, encoding='utf-8')
    print(f'    {path.name}: {sites} counter sites (verified)')


def instrument_bench(path: Path) -> None:
    t = path.read_text(encoding='utf-8')
    if "import hiTraceMeter" not in t:
        m = re.search(r'^(import .*\n)', t, re.M)
        t = t[:m.end()] + "import hiTraceMeter from '@ohos.hiTraceMeter';\n" + t[m.end():]

    # reset before the measured loop
    if 'RdbUtils.ohmStatements = 0;' not in t:
        old = ("    for (let i = 0; i < 1000; i++) {\n"
               "      await RdbUtils.insertDate('20260915');")
        new = ("    RdbUtils.ohmStatements = 0;\n"
               "    for (let i = 0; i < 1000; i++) {\n"
               "      await RdbUtils.insertDate('20260915');")
        if old in t:
            t = t.replace(old, new, 1)

    # Decide the anchor FIRST, then strip any previous marker, then re-emit once.
    # (Stripping before checking made the marker test always fail on a second run.)
    marker = "hiTraceMeter.traceByValue('OHMB/StatementCount', RdbUtils.ohmStatements);\n"
    virgin_tail = "    return 1000;\n  });\n}"
    already_tail = ("    hiTraceMeter.traceByValue('OHMB/StatementCount', RdbUtils.ohmStatements);\n"
                    "    return RdbUtils.ohmStatements;\n  });\n}")
    if virgin_tail in t:
        tail, repl = virgin_tail, ("    " + marker +
                                   "    return RdbUtils.ohmStatements;\n  });\n}")
    elif already_tail in t:
        tail, repl = already_tail, already_tail
    else:
        raise SystemExit(f'  FAILED: cannot find the bench tail in {path}')

    t = re.sub(r"[ \t]*hiTraceMeter\.traceByValue\('OHMB/StatementCount'[^\n]*\n", '', t)
    # after stripping, the anchor is either the virgin tail or the same tail without the marker
    stripped = ("    return RdbUtils.ohmStatements;\n  });\n}")
    if tail == already_tail:
        t = t.replace(stripped, repl, 1) if stripped in t else t
    else:
        t = t.replace(tail, repl, 1)
    path.write_text(t, encoding='utf-8')
    print(f'    {path.name}: emits OHMB/StatementCount')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    base = Path(a.hosts) / 'browser' / 'entry' / 'src' / 'main' / 'ets'
    rdb, bench = base / 'utils' / 'RdbUtils.ets', base / 'utils' / 'BrowserBench.ets'
    for p in (rdb, bench):
        if not p.exists():
            raise SystemExit(f'  FAILED: missing {p}')
    print('  instrumenting browser host:')
    instrument_rdb(rdb)
    instrument_bench(bench)
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
