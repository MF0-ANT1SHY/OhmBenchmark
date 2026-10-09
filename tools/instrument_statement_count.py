#!/usr/bin/env python3
"""Instrument browser_insert_date_lookup_cache so the harness counts RDB statements per save.

The case declares `rdb_statements_per_page_save` and its oracle states the expected shape
exactly:

    unfixed: >= 3 statements per page save after the first (SELECT + CREATE TABLE + INSERT)
    fixed:    1 statement per page save (INSERT only)

`RdbUtils.insertDate` is the hot path: it runs a date_table SELECT, a conditional INSERT,
and `createHistoryTable` (CREATE TABLE IF NOT EXISTS) on every call. The fix adds a
`knownDates` cache, so after the first save per date only the history INSERT remains.

This patch adds a measurement-only counter around the store operations and emits the tally
as an `OHMB/StatementCount` trace marker, which is the same mechanism the existing
ArticleCardCount / HistoryItemCount markers use, so tools/device/analyze.py can read it.

The counter is pure instrumentation: it wraps calls that already happen and changes no
control flow, no SQL and no caching behaviour. Both variants get the identical counter, so
the comparison stays fair.

Usage: python3 tools/instrument_statement_count.py [--hosts DIR] [--revert]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARK = '// OHMB statement counter (measurement only)'

COUNTER_FIELD = f"""  {MARK}
  static ohmStatements: number = 0

"""

COUNT_HELPER = f"""  {MARK}
  private static ohmCount(n: number = 1): void {{
    RdbUtils.ohmStatements += n
  }}

"""


def instrument_rdb(path: Path) -> bool:
    """Add the counter field and bump it around the store operations."""
    t = path.read_text(encoding='utf-8')
    if MARK in t:
        print(f'    {path.name}: already instrumented')
        return False

    # 1. counter field + helper, just after the class opening
    m = re.search(r'(export default class RdbUtils \{\n)', t)
    if not m:
        raise SystemExit(f'cannot find class opening in {path}')
    t = t[:m.end()] + COUNTER_FIELD + COUNT_HELPER + t[m.end():]

    # 2. count the date_table SELECT
    t = t.replace(
        'resultSet = await RdbUtils.getStore().query(predicates, ["date"]);',
        'RdbUtils.ohmCount();\n      resultSet = await RdbUtils.getStore().query(predicates, ["date"]);',
        1)

    # 3. count the conditional INSERT
    t = t.replace(
        'RdbUtils.getStore().insert("date_table", valueBucket)',
        'RdbUtils.ohmCount();\n        RdbUtils.getStore().insert("date_table", valueBucket)',
        1)

    # 4. count CREATE TABLE inside createHistoryTable
    before = t
    t = re.sub(r'(\n\s*)(await RdbUtils\.executeSql\("CREATE TABLE)',
               r'\1RdbUtils.ohmCount();\1\2', t, count=1)
    if t == before:
        # executeSql may be non-await or shaped differently; count at the call site instead
        t = t.replace('RdbUtils.executeSql("CREATE TABLE',
                      'RdbUtils.ohmCount(); RdbUtils.executeSql("CREATE TABLE', 1)

    # 5. count the history INSERT
    t = re.sub(r'(\n\s*)return RdbUtils\.getStore\(\)\.insert\(tableName, valueBucket\)',
               r'\1RdbUtils.ohmCount();\1return RdbUtils.getStore().insert(tableName, valueBucket)',
               t, count=1)

    path.write_text(t, encoding='utf-8')
    n = t.count('RdbUtils.ohmCount();')
    print(f'    {path.name}: counter added at {n} call site(s)')
    return True


def instrument_bench(path: Path) -> bool:
    """Emit the tally from the bench entry instead of a hardcoded 1000."""
    t = path.read_text(encoding='utf-8')
    if 'OHMB/StatementCount' in t and 'ohmStatements' in t:
        print(f'    {path.name}: already emitting the real count')
        return False
    if 'OhmStatementCount' in t:
        print(f'    {path.name}: has the placeholder marker; replacing with the real count')

    # reset at the start of the measured action for this case
    old_loop = """    for (let i = 0; i < 1000; i++) {
      await RdbUtils.insertDate('20260915');"""
    new_loop = """    RdbUtils.ohmStatements = 0;
    for (let i = 0; i < 1000; i++) {
      await RdbUtils.insertDate('20260915');"""
    if old_loop in t:
        t = t.replace(old_loop, new_loop, 1)

    # replace any existing marker with the measured value
    t = re.sub(r"\s*//[^\n]*measurement-only marker[^\n]*\n\s*hiTraceMeter\.traceByValue\('OHMB/StatementCount',[^\n]*\n",
               '\n', t)
    t = re.sub(r"\s*hiTraceMeter\.traceByValue\('OHMB/StatementCount',[^\n]*\n", '\n', t)

    anchor = """    return 1000;
  });
}"""
    repl = """    hiTraceMeter.traceByValue('OHMB/StatementCount', RdbUtils.ohmStatements);
    return RdbUtils.ohmStatements;
  });
}"""
    if anchor in t:
        t = t.replace(anchor, repl, 1)
    else:
        raise SystemExit(f'cannot find the bench tail to instrument in {path}')
    path.write_text(t, encoding='utf-8')
    print(f'    {path.name}: now emits the measured statement count')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    args = ap.parse_args()
    base = Path(args.hosts) / 'browser' / 'entry' / 'src' / 'main' / 'ets'
    rdb = base / 'utils' / 'RdbUtils.ets'
    bench = base / 'utils' / 'BrowserBench.ets'
    for p in (rdb, bench):
        if not p.exists():
            raise SystemExit(f'missing {p}')
    print('  instrumenting browser host:')
    instrument_rdb(rdb)
    instrument_bench(bench)
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
