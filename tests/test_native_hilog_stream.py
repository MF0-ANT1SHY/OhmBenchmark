from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from native_hilog_stream import NativeHiLogStream, logger_command


class StreamOwnershipTest(unittest.TestCase):
    def test_executable_only_platform_cmdline_and_full_argv_are_distinguished(self):
        self.assertTrue(logger_command('hilog',42))
        self.assertTrue(logger_command('\0'.join(['/system/bin/hilog','-P','42','']),42))
        self.assertFalse(logger_command('\0'.join(['hilog','-P','43','']),42))
        self.assertFalse(logger_command('another-program',42))

    def stat(self, pid, ticks):
        return f'{pid} (process) '+' '.join(['S']+['0']*18+[str(ticks)]+['0']*5)

    def stream(self, mode):
        calls = []
        stopped = False
        def shell(command):
            nonlocal stopped
            calls.append(command)
            if command.startswith('cat /proc/42/stat'):
                return self.stat(42, 123)
            if command.startswith('cat /proc/7/stat'):
                return '' if stopped else self.stat(7, 1000 if mode == 'reused' else 999)
            if command.startswith('cat /proc/7/cmdline'):
                return 'another-program\0' if mode == 'changed' else '\0'.join(['hilog','-P','42',''])
            if command == 'kill -TERM 7':
                stopped = True
                return ''
            raise AssertionError(command)
        result = NativeHiLogStream(shell, 42, '/data/local/tmp/logger-test', '/unused')
        result.owner = {'pid':7, 'start_ticks':999}
        result.app_stat = self.stat(42,123)
        result.reader = Mock()
        result.reader.poll.return_value = None
        return result, calls

    def test_pid_reuse_never_signals_the_new_process(self):
        stream, calls = self.stream('reused')
        stream.close()
        self.assertFalse(any(c.startswith('kill ') for c in calls))
        self.assertTrue(stream.closed_successfully)

    def test_changed_command_never_receives_a_signal(self):
        stream, calls = self.stream('changed')
        with self.assertRaisesRegex(RuntimeError, 'changed command'):
            stream.close()
        self.assertFalse(any(c.startswith('kill ') for c in calls))
        with self.assertRaises(RuntimeError):
            stream.receipt()

    def test_only_owned_logger_is_stopped_and_cleanup_is_idempotent(self):
        stream, calls = self.stream('owned')
        stream.close()
        stream.close()
        self.assertEqual(calls.count('kill -TERM 7'),1)
