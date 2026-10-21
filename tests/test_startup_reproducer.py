import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from export_agent_data import reproduction_script


class StartupReproducerTests(unittest.TestCase):
    def test_startup_plan_does_not_launch_before_measured_phase(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'workload.json').write_text(json.dumps({'bundle':'com.sheafreader.hm','ability':'EntryAbility',
                'setup':[{'op':'stop'}], 'measured':[{'op':'launch'}], 'verify':[]}))
            calls=[]
            def run(args, **kwargs):
                calls.append(args[-1]);return SimpleNamespace(stdout='ok')
            with patch('sys.argv', ['reproduce.py']), patch('subprocess.run', side_effect=run):
                exec(compile(reproduction_script(), str(root/'reproduce.py'), 'exec'),
                     {'__name__':'__main__','__file__':str(root/'reproduce.py')})
            self.assertEqual(sum(command.startswith('aa start') for command in calls), 1)
            self.assertTrue(calls[-1].startswith('aa start'))
