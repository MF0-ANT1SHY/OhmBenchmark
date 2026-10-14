import copy
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from accept_trace_evidence import CASE, accept, verify_capture
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


class PairedNativeAcceptanceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        folder = self.root/'cases'/CASE
        self.put(folder/'case.json', {'testcase': {'workload': 'plan.json'},
                                     'test_oracle': {'metric': 'trace_cpu_ms'}})
        self.put(folder/'plan.json', {})
        import hashlib
        self.plan_hash = hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest()
        for variant in ('unfixed', 'fixed'):
            base = self.root/'artifacts/clean'/CASE/variant
            self.put(base/'sign.json', {'audit': {'sha256': variant+'-signed'}})
            self.put(base/'workload-device.json', {'reader_refresh': {}})
            self.put(base/'workload.json', {'status': 'PASS', 'plan_sha256': self.plan_hash,
                'signed_sha256': variant+'-signed', 'reader_refresh': {},
                'fixture': {'sha256': 'ordinary-data'}, 'fixture_after': {}})
            for number in range(1, 4):
                self.put(base/'trace-captures'/f'round-{number}'/'capture.json', {
                    'case': CASE, 'variant': variant, 'round': number,
                    'plan_sha256': self.plan_hash, 'signed_sha256': variant+'-signed',
                    'fixture_sha256': 'ordinary-data', 'reader_fixture_before': {'sha256': 'ordinary-data'},
                    'reader_fixture_after': {}, 'remote_artifacts': 'private-location'})

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def check(self, low_pair=False, require_pass=True):
        def native(receipt, trace):
            value = 2000000 if receipt['variant'] == 'unfixed' else 1000000
            if low_pair and receipt['variant'] == 'fixed' and receipt['round'] == 3:
                value = 1900000
            return {'app_cpu_ns': value, 'trace_sha256': 'raw-native-hash'}
        with patch('accept_trace_evidence.ROOT', self.root), \
                patch('accept_trace_evidence.verify_preparation'), \
                patch('accept_trace_evidence.verify_observation', return_value={}), \
                patch('accept_trace_evidence.verify_capture', side_effect=native):
            return accept(CASE, write=False, require_pass=require_pass)

    def test_all_six_valid_captures_are_required_without_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.check()['unfixed']['samples'], [2, 2, 2])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        p = self.root/'artifacts/clean'/CASE/'fixed/trace-captures/round-3/capture.json'
        p.unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()

    def test_provenance_mismatch_is_not_accepted(self):
        p = self.root/'artifacts/clean'/CASE/'fixed/trace-captures/round-2/capture.json'
        data = json.loads(p.read_text())
        data['signed_sha256'] = 'another-build'
        self.put(p, data)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.check()

    def test_one_low_pair_fails_even_when_medians_improve(self):
        with self.assertRaisesRegex(ValueError, 'criterion not met'):
            self.check(low_pair=True)
        self.assertEqual(self.check(low_pair=True, require_pass=False)['unfixed']['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
