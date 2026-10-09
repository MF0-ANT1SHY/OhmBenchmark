#!/usr/bin/env python3
"""Generate the interviewapp response-log harness patch so its hunk counts cannot drift.

Editing a patch section by hand and forgetting to update its `@@ -0,0 +1,N @@` count makes
`git apply` truncate the file at N lines. That cost two rounds on this case, once for the bench
and once again after a one-line insert. The patch is therefore generated from the canonical
harness files and never hand-edited.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASE = 'interviewapp_response_log_full_stringify'
PATCH = REPO / 'device-tests' / 'patches' / CASE / 'unfixed.patch'

BENCH = '''import { common } from '@kit.AbilityKit';
import { historyStore } from './history';
import { ohmHttp } from '@itcast/basic';
import { OhmProbe } from './OhmProbe';
import { ohmResponseStringifyReset, ohmResponseStringifyTotal, ohmDiag } from '@itcast/basic';
import { OHM_FIXTURE_HOST } from './OhmFixtureHost';

interface FixtureRow { id: number; title: string; description: string; }

export async function runInterviewBench(context: common.UIAbilityContext, name: string): Promise<void> {
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    if (name === 'interviewapp_response_log_full_stringify') {
      // OHM_FIXTURE_HOST is written by tools/instrument_response_stringify.py, so the fixture
      // can be pointed at whatever address the device can actually reach
      ohmHttp.baseURL = 'http://' + OHM_FIXTURE_HOST + ':18766/';
      return;
    }
    historyStore.clear();
    if (name === 'interviewapp_search_history_unbounded') {
      for (let i=0;i<5000;i++) historyStore.setItem('HarmonyOS interview question '+i);
    }
    await new Promise<void>((resolve) => { setTimeout(resolve, 2500); });
  }, async (): Promise<number> => {
    if (name === 'interviewapp_search_history_unbounded') {
      let total=0;
      for (let i=0;i<100;i++) total+=historyStore.getAll().length;
      return total;
    }
    if (name === 'interviewapp_response_log_full_stringify') {
      // count how many full response bodies the handler serializes for logging: the fixture
      // returns a 345 KB body, so this is the oracle's O(payload) cost driver
      ohmResponseStringifyReset();
      let total=0;
      for (let i=0;i<5;i++) {
        const response = await ohmHttp.get<FixtureRow[]>('response');
        total+=response.data.length;
      }
      const stringifies = ohmResponseStringifyTotal();
      ohmDiag(context, 'after-wait', 'calls=5 serializes=' + stringifies +
        ' rowsPerResponse=' + (total / 5));
      return stringifies;
    }
    for (let i=0;i<1000;i++) historyStore.setItem('HarmonyOS interview question '+i);
    // Include the application's own deferred flush (2 seconds) in both windows.
    await new Promise<void>((resolve) => { setTimeout(resolve, 3000); });
    return historyStore.getAll().length;
  });
}
'''


def new_file_section(path: str, body: str) -> str:
    """A git 'new file' section, with the hunk header computed from the body."""
    lines = body.splitlines()
    added = ''.join('+' + ln + '\n' for ln in lines)
    return (f'diff --git a/{path} b/{path}\n'
            f'new file mode 100644\n'
            f'index 0000000..1111111\n'
            f'--- /dev/null\n'
            f'+++ b/{path}\n'
            f'@@ -0,0 +1,{len(lines)} @@\n' + added)


def main() -> int:
    probe = (REPO / 'device-tests' / 'harness' / 'OhmProbe.ets').read_text(encoding='utf-8')
    base = 'features/home/src/main/ets/utils'
    sections = [
        new_file_section(f'{base}/OhmProbe.ets', probe),
        new_file_section(f'{base}/InterviewBench.ets', BENCH),
    ]
    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_text('\n'.join(sections), encoding='utf-8')
    print(f'  wrote {PATCH.relative_to(REPO)}: '
          f'{len(PATCH.read_text(encoding="utf-8").splitlines())} lines, '
          f'probe {len(probe.splitlines())}, bench {len(BENCH.splitlines())}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
