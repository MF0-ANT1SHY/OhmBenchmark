import copy
import unittest
from unittest.mock import patch

from weather_session_gc_memory import verify_gc_receipts


def fixture():
    def sample(phase, t, pss):
        return dict(phase=phase, read_start_monotonic=t, monotonic=t + .1,
                    pid=123, process_start_ticks=456, pss_bytes=pss)
    before = [sample('before', t, 100) for t in (12, 13, 14)]
    after = [sample('after', t, 200) for t in (42, 43, 44)]
    def receipt(phase, start):
        return dict(phase=phase, pid=123, command='hidumper --mem-jsheap 123 --gc',
                    native_exit_code=0, raw_output='\n__WEATHER_GC_EXIT__=0\n',
                    start_monotonic=start, end_monotonic=start + 1,
                    settle_end_monotonic=start + 11, settle_seconds=10)
    return dict(baseline_samples=before, post_samples=after,
                snapshots=[before[-1], sample('workload', 25, 180), after[-1]],
                action_start_monotonic=15, action_end_monotonic=29,
                gc_requests=[receipt('before', 1), receipt('after', 30)])


class ReceiptTests(unittest.TestCase):
    # Kernel field parsing itself is covered by system_pss; isolate chronology here.
    @patch('weather_session_gc_memory.verify_extra')
    def test_complete_boundaries(self, verify):
        self.assertEqual(verify_gc_receipts(fixture())['lower_bytes'], 100)
        self.assertEqual(verify.call_count, 7)

    @patch('weather_session_gc_memory.verify_extra')
    def test_failed_native_exit_short_wait_wrong_pid_and_early_sampling(self, _):
        for field, value in [('raw_output', '__WEATHER_GC_EXIT__=1'),
                             ('native_exit_code', 1), ('pid', 999),
                             ('settle_end_monotonic', 40),
                             ('settle_end_monotonic', 43),
                             ('command', 'hidumper --mem-jsheap 123'),
                             ('start_monotonic', 28)]:
            with self.subTest(field=field, value=value):
                record = copy.deepcopy(fixture())
                record['gc_requests'][1][field] = value
                with self.assertRaises(ValueError):
                    verify_gc_receipts(record)

    @patch('weather_session_gc_memory.verify_extra')
    def test_baseline_cannot_include_measured_work(self, _):
        record = fixture()
        record['action_start_monotonic'] = 13
        with self.assertRaisesRegex(ValueError, 'baseline overlaps'):
            verify_gc_receipts(record)
