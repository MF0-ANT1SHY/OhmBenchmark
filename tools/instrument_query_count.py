#!/usr/bin/env python3
"""Count RDB read queries by inserting an inline counter before each query call.

Two earlier shapes failed or were risky:
  - wrapping each call in a closure: ArkTS rejects it ("Object is possibly 'null'")
    because the closure hides the store's null-narrowing;
  - rewriting to custom accessors: needs loose typing to compile.

This shape does neither. It only *prepends* a statement that increments a counter, leaving
the original expression untouched, so null-narrowing, types and control flow are unchanged:

    const resultSet = await this.store.querySql(sql, args);
becomes
    DatabaseManager.ohmQueries++; const resultSet = await this.store.querySql(sql, args);

Identical in both variants. Only reads are counted, which is what these oracles ask for.

Usage:
    python3 tools/instrument_query_count.py --file DatabaseManager.ets --bench SheafBench.ets
"""
import argparse
import re
import sys
from pathlib import Path

MARK = '// OHMB query counter (measurement only)'


def store_field(src: str) -> str:
    m = re.search(r'this\.(\w+)\.querySql\(', src) or re.search(r'this\.(\w+)\.query\(', src)
    if not m:
        raise SystemExit('cannot find the store field used for queries')
    return m.group(1)


def strip_previous(t: str) -> str:
    """Remove earlier instrumentation so the tool is idempotent."""
    t = re.sub(r'[ \t]*// OHMB query counter \(measurement only\)\n', '', t)
    t = re.sub(r'[ \t]*\w+\.ohmQueries\+\+;\n', '', t)
    t = re.sub(r'[ \t]*static ohmQueries: number = 0\n\n?', '', t)
    return t


def instrument_db(path: Path) -> None:
    t = strip_previous(path.read_text(encoding='utf-8'))
    field = store_field(t)
    cls = re.search(r'export class (\w+)', t).group(1)

    # counter field only; no helper methods
    m = re.search(r'(export class \w+ \{\n)', t)
    t = t[:m.end()] + f'  {MARK}\n  static ohmQueries: number = 0\n\n' + t[m.end():]

    total = 0
    for call in ('querySql', 'query'):
        pat = re.compile(r'([ \t]*)const\s+(\w+)(\s*:\s*[\w.<>\[\]]+)?\s*=\s*await\s+this\.'
                         + field + r'\.' + call + r'\(')
        def repl(mm):
            nonlocal total
            total += 1
            indent, name, typ = mm.group(1), mm.group(2), mm.group(3) or ''
            return (f'{indent}{cls}.ohmQueries++;\n'
                    f'{indent}const {name}{typ} = await this.{field}.{call}(')
        t = pat.sub(repl, t)

        # also handle `return await this.store.queryX(...)`
        pat2 = re.compile(r'([ \t]*)return\s+await\s+this\.' + field + r'\.' + call + r'\(')
        def repl2(mm):
            nonlocal total
            total += 1
            return f'{mm.group(1)}{cls}.ohmQueries++;\n{mm.group(1)}return await this.{field}.{call}('
        t = pat2.sub(repl2, t)

    path.write_text(t, encoding='utf-8')
    print(f'  {path.name}: counter added before {total} query site(s)')
    if total == 0:
        print('    WARNING: no sites matched; counts will be 0')


def instrument_bench(path: Path, cls: str) -> None:
    t = path.read_text(encoding='utf-8')
    if 'OHMB/QueryCount' in t:
        print(f'  {path.name}: already emits the query count')
        return
    if f'import {{ {cls} }}' not in t:
        m = re.search(r'^(import .*\n)', t, re.M)
        t = t[:m.end()] + f"import {{ {cls} }} from '../data/{cls}';\n" + t[m.end():]
    if 'import hiTraceMeter' not in t:
        m = re.search(r'^(import .*\n)', t, re.M)
        t = t[:m.end()] + "import hiTraceMeter from '@ohos.hiTraceMeter';\n" + t[m.end():]

    old = ("    if (name === 'sheafreader_unread_counts_n_plus_1') {\n"
           "      const feeds = await FeedService.getInstance().getFeedsWithCounts();")
    new = ("    if (name === 'sheafreader_unread_counts_n_plus_1') {\n"
           f"      {cls}.ohmQueries = 0;\n"
           "      const feeds = await FeedService.getInstance().getFeedsWithCounts();")
    if old in t:
        t = t.replace(old, new, 1)
    else:
        print(f'    WARNING: reset anchor not found in {path.name}')

    tail = "      let sum = 0; for (const f of feeds) sum += f.unreadCount;\n      return sum;"
    if tail in t:
        t = t.replace(
            tail,
            "      let sum = 0; for (const f of feeds) sum += f.unreadCount;\n"
            f"      hiTraceMeter.traceByValue('OHMB/QueryCount', {cls}.ohmQueries);\n"
            "      return sum;", 1)
    else:
        print(f'    WARNING: emit anchor not found in {path.name}')
    path.write_text(t, encoding='utf-8')
    print(f'  {path.name}: emits OHMB/QueryCount')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file')
    ap.add_argument('--bench')
    ap.add_argument('--hosts', help='hosts dir; derives the sheafreader paths when given')
    ap.add_argument('--class', dest='cls', default='DatabaseManager')
    a = ap.parse_args()

    if a.hosts and not (a.file and a.bench):
        base = Path(a.hosts) / 'sheafreader' / 'entry' / 'src' / 'main' / 'ets'
        a.file = str(base / 'data' / 'DatabaseManager.ets')
        a.bench = str(base / 'utils' / 'SheafBench.ets')
    if not (a.file and a.bench):
        sys.exit('give either --hosts, or both --file and --bench')

    db, bench = Path(a.file), Path(a.bench)
    for p in (db, bench):
        if not p.exists():
            sys.exit(f'missing {p}')
    instrument_db(db)
    instrument_bench(bench, a.cls)
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
