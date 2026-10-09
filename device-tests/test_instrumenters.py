#!/usr/bin/env python3
"""Check the instrumenters against a synthetic fixture - no device, no network.

Both instrumenters work by rewriting ArkTS source, and both had real bugs found only by a
full device cycle: a missed call site (wrong indentation assumption) that produced a tree
which failed to compile, and a marker check that always failed on a second run. Those bugs
were invisible in a green build because they only showed up one step later.

This test exercises the rewriting rules directly so a regression is caught here rather than
20 minutes into a device run.

Usage: python3 device-tests/test_instrumenters.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

RDB_FIXTURE = """export default class RdbUtils {
  private static rdbStore: relationalStore.RdbStore

  static async createHistoryTable(tableName: string) {
    const sql = `CREATE TABLE IF NOT EXISTS ${tableName} (id INTEGER)`
    try {
      await RdbUtils.executeSql(sql)
    } catch (error) {
      console.error(error.code)
    }
  }

  static async insertDate(date: string) {
    const predicates = new relationalStore.RdbPredicates("date_table")
    let resultSet: relationalStore.ResultSet
    try {
      resultSet = await RdbUtils.getStore().query(predicates, ["date"]);
      if (resultSet.rowCount <= 0) {
        const valueBucket: relationalStore.ValuesBucket = { "date": date }
        RdbUtils.getStore().insert("date_table", valueBucket)
      }
      resultSet.close()
    } catch (error) {
      console.error(error)
    }
    await RdbUtils.createHistoryTable(date)
  }

  static async insertHistory(tableName: string, history: History) {
    tableName = "history_" + tableName
    const valueBucket: relationalStore.ValuesBucket = { "title": history.title }
    return RdbUtils.getStore().insert(tableName, valueBucket)
  }
}
"""

BENCH_FIXTURE = """import { OhmProbe } from './OhmProbe';

export async function runBrowserBench(context: common.UIAbilityContext, name: string): Promise<void> {
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    return;
  }, async (): Promise<number> => {
    for (let i = 0; i < 1000; i++) {
      await RdbUtils.insertDate('20260915');
    }
    return 1000;
  });
}
"""


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base = root / 'hosts' / 'browser' / 'entry' / 'src' / 'main' / 'ets' / 'utils'
        base.mkdir(parents=True)
        rdb, bench = base / 'RdbUtils.ets', base / 'BrowserBench.ets'
        rdb.write_text(RDB_FIXTURE)
        bench.write_text(BENCH_FIXTURE)

        tool = REPO / 'tools' / 'instrument_statement_count.py'
        rc, out = run([sys.executable, str(tool), '--hosts', str(root / 'hosts')], REPO)
        print('statement counter, first run:')
        print('  ' + out.strip().replace('\n', '\n  '))
        if rc != 0:
            fails.append('statement counter failed on a clean fixture')
        text = rdb.read_text()
        n = text.count('RdbUtils.ohmCount();')
        if n != 4:
            fails.append(f'expected 4 counter sites, got {n}')
        if text.count('static ohmStatements') != 1:
            fails.append('counter field declared more than once')
        if bench.read_text().count('OHMB/StatementCount') != 1:
            fails.append('bench must emit OHMB/StatementCount exactly once')

        # idempotency: a second run must be a no-op, not an error
        rc2, out2 = run([sys.executable, str(tool), '--hosts', str(root / 'hosts')], REPO)
        print('statement counter, second run:')
        print('  ' + out2.strip().replace('\n', '\n  '))
        if rc2 != 0:
            fails.append('statement counter is not idempotent (second run failed)')
        text2 = rdb.read_text()
        if text2.count('RdbUtils.ohmCount();') != 4:
            fails.append(f'second run changed the site count to '
                         f'{text2.count("RdbUtils.ohmCount();")}')
        if bench.read_text().count('OHMB/StatementCount') != 1:
            fails.append('second run duplicated the bench marker')

    print()
    if fails:
        for f in fails:
            print(f'  FAIL  {f}')
        return 1
    print('  all instrumenter checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
