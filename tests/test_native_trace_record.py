from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from native_trace_record import BUNDLE, cpu_set, record, process


class NativeTraceOwnershipTest(unittest.TestCase):
    def test_foreign_observer_cannot_start_ui_or_trace(self):
        class Observer:
            bundle = 'another.app'
            receipt_key = 'wan_history'
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            record(None, {'bundle': 'org.example.wan.ohos'}, folder, Observer())

    def test_process_identity_is_exact_not_a_bundle_substring(self):
        def shell(command):
            if command.startswith('pidof '):return '123'
            if command.endswith('/cmdline'):return BUNDLE+'.other\x00'
            return '123 (app) S 0'
        with self.assertRaisesRegex(ValueError,'provenance'):process(shell)

    def test_online_cpu_ranges_are_native_and_bounded(self):
        self.assertEqual(cpu_set('0-3,6,8-11\n'), [0, 1, 2, 3, 6, 8, 9, 10, 11])
        for value in ('', '4-2', '0-300', 'command failed'):
            with self.assertRaises(ValueError):
                cpu_set(value)

    def test_existing_profiler_prevents_ui_and_stop_commands(self):
        class UI:
            def __init__(self): self.calls = []
            def shell(self, command):
                self.calls.append(command)
                return '123' if command == 'pidof hiperf' else '0'
            def run(self, actions): raise AssertionError('another capture was disturbed')
        ui = UI()
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            record(ui, {'bundle': BUNDLE}, Path(folder))
        self.assertEqual(ui.calls, ['pidof hiperf'])

    def test_our_bad_clock_capture_is_stopped_and_failure_retained(self):
        class UI:
            def __init__(self): self.active = False; self.calls = []; self.buffer = 18432
            def shell(self, command):
                self.calls.append(command)
                if command == 'pidof hiperf': return ''
                if command.endswith('/tracing_on'): return str(int(self.active))
                if command.endswith('/online'): return '0-1'
                if command.startswith('cat ') and command.endswith('/buffer_size_kb'): return str(self.buffer)
                if command.startswith('echo 18432 > '): self.buffer = 18432; return ''
                if command.startswith('hitrace --trace_begin'):
                    if '--text' in command:raise AssertionError('long and short recording modes cannot coexist')
                    self.active = True; self.buffer = 65536; return 'OpenRecording done'
                if command.endswith('/trace_clock'): return '[mono] boot'
                if command == 'hitrace --trace_finish_nodump':
                    self.active = False; return 'Trace Closed'
                raise AssertionError(command)
            def run(self, actions): pass
            def find(self, selector, timeout): return {}
        ui = UI()
        with tempfile.TemporaryDirectory() as folder, patch('native_trace_record.read_state', return_value={}), \
                patch('native_trace_record.process', return_value={'pid': 42}):
            result = record(ui, {'bundle': BUNDLE, 'setup': []}, folder)
            self.assertEqual(result['status'], 'FAIL')
            self.assertIn('boot clock', result['error'])
            self.assertTrue((Path(folder)/'capture.json').exists())
        self.assertFalse(ui.active)
        self.assertIn('hitrace --trace_finish_nodump', ui.calls)
        self.assertEqual(ui.buffer, 18432)


if __name__ == '__main__':
    unittest.main()
