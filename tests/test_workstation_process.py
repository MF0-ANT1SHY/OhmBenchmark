import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from workstation_process import identity
from rss_service_fixture import prepare, same_instance


class WorkstationIdentityTests(unittest.TestCase):
    def test_live_process_is_stable(self):
        first = identity(os.getpid())
        self.assertEqual(first, identity(os.getpid()))
        self.assertGreater(first['start_ticks'], 0)
        self.assertTrue(first['command'])

    def test_invalid_pid_never_runs_shell(self):
        for pid in (0, -1, True, '12; exit'):
            with self.assertRaises(ValueError):
                identity(pid)

    def test_generated_rss_verifier_compiles(self):
        class Remote:
            def python(self, code, data, timeout):
                compile(code, '<remote-rss-proof>', 'exec')
                return '{}'
        prepare(Remote(), {'id': 'sheafreader_refresh_feeds_sequential',
                          'host_app': {'bundle_name': 'com.sheafreader.hm'}}, {'body_bytes': 256})

    def test_network_condition_change_is_rejected(self):
        record = dict(sha256='data', source_sha256='source', base_url='url',
                      service_pid=1, service_start_ticks=10, network_delay_s=1.5,
                      launcher_sha256='launcher')
        same_instance(record, dict(record))
        with self.assertRaises(ValueError):
            same_instance(record, {**record, 'network_delay_s': 0})
        with self.assertRaises(ValueError):
            same_instance(record, {**record, 'launcher_sha256': 'other'})
