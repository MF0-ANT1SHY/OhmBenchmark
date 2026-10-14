import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from accept_trace_evidence import verify_capture
from rss_refresh_progress import verify_refresh, REFRESH_BUTTON
from scheduler_cpu import compute, window_from_markers
import json


def switch(cpu, stamp, previous, owner, following):
    return (f' worker-{previous} ({owner}) [{cpu:03}] .... {stamp}: sched_switch: '
            f'prev_comm=worker prev_pid={previous} prev_prio=120 prev_state=R ==> '
            f'next_comm=worker next_pid={following} next_prio=120\n')


class NativeTraceEvidenceTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.trace = Path(directory.name)/'trace.htrace'
        token = 'a' * 32
        self.trace.write_text(''.join([
            switch(0, '1.000000', 0, 0, 100), switch(0, '1.004000', 100, 100, 101),
            switch(0, '1.010000', 101, 100, 0), switch(1, '1.000000', 0, 0, 999),
            switch(1, '1.005000', 999, 999, 102), switch(1, '1.007000', 102, 100, 999),
            switch(1, '1.010000', 999, 999, 0),
            f' sh-990 (990) [000] .... 1.003000: tracing_mark_write: W:{token}:begin\n',
            f' sh-991 (991) [000] .... 1.009000: tracing_mark_write: W:{token}:end\n']))
        def feeds(value, start, end):
            return {'raw_rows': json.dumps([{'url': f'http://127.0.0.1:18491/feeds/{i}.xml',
                    'last_fetched': value} for i in range(1, 11)]),
                    'started_monotonic': start, 'ended_monotonic': end}
        before, after = feeds(1, 1, 2), feeds(2, 5, 6)
        progress = {'before': before, 'after': after,
                    'button_after': {**REFRESH_BUTTON, 'enabled': 'true', 'bundleName': 'com.sheafreader.hm'},
                    'progress': verify_refresh(before, after)}
        process = {'pid': 100, 'command': 'com.sheafreader.hm\0', 'start_ticks': 123}
        started, ended = window_from_markers(self.trace, token, [100])
        self.receipt = {'status': 'CAPTURED', 'marker_token': token, 'pids': [100],
            'process_before': process, 'process_after': copy.deepcopy(process),
            'online_cpus_before': [0, 1], 'online_cpus_after': [0, 1],
            'clock_before': '[boot] mono', 'clock_after': '[boot] mono',
            'buffer_size_kb_before': 18432, 'buffer_size_kb_after': 18432,
            'reader_refresh': progress, 'action_start_monotonic': 3, 'action_end_monotonic': 7,
            'scheduler_cpu': compute(self.trace, [100], started, ended, [0, 1])}

    def test_cpu_is_recomputed_from_native_intervals_not_wall_time(self):
        result = verify_capture(self.receipt, self.trace)
        self.assertEqual(result['app_cpu_ms'], 8)
        self.assertEqual(result['window_end_ns'] - result['window_start_ns'], 6000000)

    def test_forged_cpu_receipt_is_rejected(self):
        self.receipt['scheduler_cpu']['app_cpu_ns'] = 1
        with self.assertRaisesRegex(ValueError, 'raw native'):
            verify_capture(self.receipt, self.trace)

    def test_changed_identity_and_environment_are_rejected(self):
        for key, value in (('process_after', {'pid': 100, 'command': 'com.sheafreader.hm', 'start_ticks': 124}),
                           ('clock_after', '[mono] boot'), ('buffer_size_kb_after', 65536),
                           ('online_cpus_after', [0])):
            altered = copy.deepcopy(self.receipt)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_capture(altered, self.trace)

    def test_completion_after_recording_and_trace_tampering_are_rejected(self):
        altered = copy.deepcopy(self.receipt)
        altered['action_end_monotonic'] = 5.5
        with self.assertRaises(ValueError):
            verify_capture(altered, self.trace)
        self.trace.write_text(self.trace.read_text().replace('1.007000', '1.008000'))
        with self.assertRaises(ValueError):
            verify_capture(self.receipt, self.trace)


if __name__ == '__main__':
    unittest.main()
