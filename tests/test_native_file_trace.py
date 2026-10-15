from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from native_file_trace import record


class FailedTraceTest(unittest.TestCase):
    def test_failed_business_action_preserves_partial_trace_and_restores_state(self):
        state={'on':'0','buffer':'512'}
        commands=[]
        def shell(command):
            commands.append(command)
            if command.startswith('pidof '):return ''
            if command.endswith('/events/enable'):return '0'
            if command.endswith('/tracing_on'):return state['on']
            if command.endswith('/buffer_size_kb') and command.startswith('cat '):return state['buffer']
            if command.endswith('/online'):return '0-1'
            if command.startswith('hitrace --trace_begin'):
                state.update(on='1',buffer='16384');return 'OpenRecording done.'
            if command.startswith('hitrace --trace_finish -o '):
                state['on']='0';return 'Trace Closed.'
            if command.startswith('echo 512 > '):state['buffer']='512';return ''
            if command.startswith('rm -f '):return ''
            raise AssertionError(command)
        def action():
            exc=RuntimeError('normal request did not complete')
            exc.observation={'last_native_page':1}
            raise exc
        def transfer(args,**kwargs):Path(args[-1]).write_bytes(b'original partial native trace')
        with tempfile.TemporaryDirectory() as tmp, patch('native_file_trace.markers'), patch('native_file_trace.subprocess.run',side_effect=transfer):
            folder=Path(tmp)/'capture';receipt=record(shell,action,folder)
            self.assertEqual(receipt['status'],'FAIL')
            self.assertEqual(receipt['error'],'normal request did not complete')
            self.assertEqual(receipt['failure_observation'],{'last_native_page':1})
            self.assertEqual((folder/'failure-trace.txt').read_bytes(),b'original partial native trace')
            self.assertEqual(state,{'on':'0','buffer':'512'})
            self.assertFalse(any('finish_nodump' in command for command in commands))
