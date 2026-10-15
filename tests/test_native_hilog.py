import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from native_hilog import snapshot

class NativeHilogTest(unittest.TestCase):
    def test_incomplete_native_utf8_preserves_exact_bytes_and_ascii_callback_identity(self):
        raw=b'100.000000001 20 21 I app: response: '+b'\xe4\xb8'
        with tempfile.TemporaryDirectory() as temporary,patch('native_hilog.subprocess.run',return_value=subprocess.CompletedProcess([],0,raw,b'')) as run:
            result=snapshot(20,temporary,'after')
            self.assertEqual(Path(result['raw_file']).read_bytes(),raw)
            self.assertEqual(result['raw_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertTrue(result['replacement_decoding_used']);self.assertIn('100.000000001 20 21',result['raw_logs'])
            self.assertEqual(Path(result['raw_file']).stat().st_mode&0o777,0o600)
            self.assertNotIn('text',run.call_args.kwargs)
            with self.assertRaises(FileExistsError):snapshot(20,temporary,'after')
    def test_valid_utf8_and_command_failure_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary,patch('native_hilog.subprocess.run',return_value=subprocess.CompletedProcess([],0,b'normal',b'')):
            self.assertTrue(snapshot(20,temporary,'valid')['strict_utf8'])
        with tempfile.TemporaryDirectory() as temporary,patch('native_hilog.subprocess.run',return_value=subprocess.CompletedProcess([],1,b'partial',b'failure')):
            with self.assertRaises(RuntimeError):snapshot(20,temporary,'failed')
            self.assertEqual((Path(temporary)/'failed.stdout.bin').read_bytes(),b'partial')
    def test_invalid_snapshot_identity_cannot_execute_a_command(self):
        with patch('native_hilog.subprocess.run') as run:
            for pid,label in [(0,'after'),(True,'after'),(20,'../secret')]:
                with self.assertRaises(ValueError):snapshot(pid,'unused',label)
            run.assert_not_called()
