import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from remote_device import Remote


class RemoteWindowsTest(unittest.TestCase):
    def test_native_source_and_payload_are_stdin_not_shell_arguments(self):
        source = 'print(PAYLOAD)\n'
        payload = {'text': '`literal` $(literal) 中文\n"quoted"'}
        result = subprocess.CompletedProcess([], 0, b'ok\n', b'')
        with patch('remote_device.subprocess.run', return_value=result) as run:
            self.assertEqual(Remote('HKRC_2').python(source, payload), 'ok\n')
        args, kwargs = run.call_args
        self.assertEqual(args[0][-1], 'python -X utf8 -')
        script = kwargs['input'].decode()
        scope = {}
        exec(script.split('print(PAYLOAD)')[0], scope)
        self.assertEqual(scope['PAYLOAD'], payload)
        self.assertNotIn(payload['text'], ' '.join(args[0]))

    def test_existing_wsl_transport_is_retained(self):
        result = subprocess.CompletedProcess([], 0, b'ok', b'')
        with patch('remote_device.subprocess.run', return_value=result) as run:
            Remote().python('print(1)')
        self.assertEqual(run.call_args.args[0][-1], 'wsl -d Ubuntu-24.04 -- bash -s')
        self.assertTrue(run.call_args.kwargs['input'].startswith(b"python3 - <<'OHM_REMOTE_PY'"))

    def test_invalid_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            Remote(backend='unknown')
