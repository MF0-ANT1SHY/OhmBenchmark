from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from ui_driver import UI

URL = 'https://www.wanandroid.com/blog/show/3942'


class NativeWebCompletionBarrierTest(unittest.TestCase):
    def line(self, i, message, pid=42):
        return f'100.{i:09d} {pid} 43 I A00000/org.example.wan.ohos/WebPage: {message}'

    def run_barrier(self, messages, changed_ticks=False):
        observations = iter(['', *messages])
        seen, taps = [], []
        stat_reads = 0
        def shell(command):
            nonlocal stat_reads
            seen.append(command)
            if command.startswith('pidof '):
                return '42'
            if command.startswith('cat /proc/'):
                stat_reads += 1
                ticks = '1000' if changed_ticks and stat_reads > 1 else '999'
                return '42 (wan) '+' '.join(['S']+['0']*18+[ticks]+['0']*5)
            if command.startswith('hilog '):
                return next(observations)
            raise AssertionError(command)
        ui = UI(shell, 'org.example.wan.ohos')
        ui.tap = lambda selector: taps.append(selector)
        with patch('ui_driver.time.sleep'), patch('ui_driver.time.monotonic', side_effect=[0, 1, 61]):
            ui.refresh_wan_web({'id': 'refresh'}, URL)
        return seen, taps

    def normal(self):
        return '\n'.join([self.line(1, 'onPageBegin url: '+URL),
                          self.line(2, 'onPageEnd url: '+URL),
                          self.line(3, 'onTitleReceive title: real weekly')])

    def test_waits_for_late_title_without_another_refresh(self):
        partial = '\n'.join(self.normal().splitlines()[:2])
        commands, taps = self.run_barrier([partial, self.normal()])
        self.assertEqual(taps, [{'id': 'refresh'}])
        self.assertEqual(sum(c.startswith('hilog ') for c in commands), 3)

    def test_errors_overlap_foreign_pid_redirect_or_changed_process_fail(self):
        for kind in ('error', 'overlap', 'pid', 'redirect', 'ticks'):
            text = self.normal()
            if kind == 'error':
                text += '\n'+self.line(4, 'onErrorReceive url: '+URL)
            if kind == 'overlap':
                text += '\n'+self.line(4, 'onPageBegin url: '+URL)
            if kind == 'pid':
                text = text.replace(' 42 43 ', ' 99 43 ')
            if kind == 'redirect':
                text = text.replace(URL, 'https://unrelated.example/')
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                self.run_barrier([text], changed_ticks=kind == 'ticks')

    def test_no_completion_cannot_be_accepted_due_to_timeout(self):
        with self.assertRaisesRegex(RuntimeError, 'did not complete'):
            self.run_barrier(['', ''])

    def test_transport_failure_is_not_hidden_as_a_page_wait(self):
        def shell(command):
            raise RuntimeError('transport offline')
        ui = UI(shell, 'org.example.wan.ohos')
        with self.assertRaisesRegex(RuntimeError, 'transport offline'):
            ui.refresh_wan_web({}, URL)
