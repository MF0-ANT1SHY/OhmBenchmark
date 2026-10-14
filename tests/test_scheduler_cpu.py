from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from scheduler_cpu import compute, timestamp_ns, window_from_markers


def event(cpu, stamp, previous, owner, following):
    return (f' worker-{previous} ({owner}) [{cpu:03}] .... {stamp}: sched_switch: '
            f'prev_comm=worker prev_pid={previous} prev_prio=120 prev_state=R ==> '
            f'next_comm=worker next_pid={following} next_prio=120\n')


class SchedulingCPUTimeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'trace.htrace'
        self.events = [event(0, '1.000000', 0, 0, 100), event(0, '1.004000', 100, 100, 101),
                       event(0, '1.010000', 101, 100, 0), event(1, '1.000000', 0, 0, 999),
                       event(1, '1.005000', 999, 999, 102), event(1, '1.007000', 102, 100, 999),
                       event(1, '1.010000', 999, 999, 0)]

    def calculate(self, events=None, header=''):
        self.path.write_text(header + ''.join(self.events if events is None else events))
        return compute(self.path, [100], 1003000000, 1009000000, [0, 1])

    def test_all_app_threads_are_clipped_and_other_process_excluded(self):
        result = self.calculate()
        self.assertEqual(result['app_cpu_ns'], 8000000)
        self.assertEqual(result['per_thread_ns'], {'100': 1000000, '101': 5000000, '102': 2000000})

    def test_missing_switch_and_incomplete_cpu_coverage_rejected(self):
        for index in (1, 2, 6):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.calculate(self.events[:index] + self.events[index+1:])

    def test_unknown_owner_cannot_be_silently_excluded(self):
        changed = list(self.events)
        changed[2] = changed[2].replace('(100)', '(-----)')
        with self.assertRaisesRegex(ValueError, 'TGID attribution'):
            self.calculate(changed)

    def test_thread_reuse_and_out_of_order_events_rejected(self):
        changed = list(self.events)
        changed[2] = changed[2].replace('worker-101 (100)', 'worker-100 (200)').replace('prev_pid=101', 'prev_pid=100')
        with self.assertRaises(ValueError):
            self.calculate(changed)
        with self.assertRaises(ValueError):
            self.calculate(list(reversed(self.events)))

    def test_reported_loss_overflow_and_truncated_event_rejected(self):
        for header in ('CPU:0 [LOST 5 EVENTS]\n', '# entries-in-buffer/entries-written: 10/11\n'):
            with self.assertRaises(ValueError):
                self.calculate(header=header)
        with self.assertRaises(ValueError):
            self.calculate(self.events + ['garbage sched_switch: prev_pid=42\n'])

    def test_nanosecond_precision_is_not_rounded(self):
        self.assertEqual(timestamp_ns('2397924.123456789'), 2397924123456789)
        with self.assertRaises(ValueError):
            timestamp_ns('1.1234567891')

    def test_native_clock_markers_must_be_external_unique_and_complete(self):
        token = 'a' * 32
        begin = f' sh-999 (999) [000] .... 1.003000: tracing_mark_write: W:{token}:begin\n'
        end = f' sh-998 (998) [001] .... 1.009000: tracing_mark_write: W:{token}:end\n'
        self.path.write_text(begin + end)
        self.assertEqual(window_from_markers(self.path, token, [100]), (1003000000, 1009000000))
        for raw in (begin, begin + begin + end, begin.replace('(999)', '(100)') + end, end + end):
            self.path.write_text(raw)
            with self.assertRaises(ValueError):
                window_from_markers(self.path, token, [100])

    def test_incoming_context_and_native_idle_alias_keep_the_same_cpu_total(self):
        changed=[]
        import re
        for line in self.events:
            following=int(re.search(r'next_pid=(\d+)',line)[1])
            owner=100 if following in (100,101,102) else following
            prefix=re.match(r'.*?\[\d+\]',line)[0]
            if following:
                replacement=re.sub(r'worker-\d+ \(\d+\)',f'worker-{following} ({owner})',prefix)
            else:
                cpu=int(re.search(r'\[(\d+)\]',prefix)[1])
                replacement=re.sub(r'worker-\d+ \(\d+\)',f'tppmgr-idle-{cpu}-{187+cpu} (2)',prefix)
            changed.append(line.replace(prefix,replacement,1))
        self.assertEqual(self.calculate(changed)['app_cpu_ns'],8000000)

    def test_unrelated_prefix_or_wrong_idle_cpu_is_not_attributed(self):
        changed=list(self.events)
        changed[0]=changed[0].replace('worker-0 (0)','stranger-555 (555)')
        with self.assertRaises(ValueError):self.calculate(changed)

    def test_anonymous_native_idle_requires_matching_payload_cpu_and_kernel_tgid(self):
        changed=list(self.events)
        changed[0]=changed[0].replace('worker-0 (0)', 'worker-100 (100)')
        changed[1]=changed[1].replace('worker-100 (100)', 'worker-101 (100)')
        changed[2]=changed[2].replace('worker-101 (100)', '<...>-187 (2)').replace(
            'next_comm=worker', 'next_comm=tppmgr-idle-0')
        self.assertEqual(self.calculate(changed)['app_cpu_ns'],8000000)
        for replacement in ('next_comm=tppmgr-idle-1', 'next_comm=worker'):
            bad=list(changed)
            bad[2]=bad[2].replace('next_comm=tppmgr-idle-0',replacement)
            with self.assertRaises(ValueError):self.calculate(bad)
        bad=list(changed);bad[2]=bad[2].replace('(2)', '(100)')
        with self.assertRaises(ValueError):self.calculate(bad)


if __name__ == '__main__':
    unittest.main()
