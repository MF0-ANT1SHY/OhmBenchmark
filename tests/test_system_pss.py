import sys
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from system_pss import pss_bytes,read_process,start_ticks,capture_window


class ProcessMemoryTests(unittest.TestCase):
    def stat(self,ticks):
        return '123 (app name (with spaces)) '+' '.join(['S']+['0']*18+[str(ticks)]+['0']*4)

    def test_total_not_rss_or_anonymous_subset(self):
        raw='Rss: 99999 kB\nPss: 2048 kB\nPss_Anon: 1000 kB\nPss_File: 1048 kB\n'
        self.assertEqual(pss_bytes(raw),2097152)

    def test_missing_duplicate_and_wrong_units_rejected(self):
        for raw in ['Pss_Anon: 2048 kB','Pss: 12 MB','Pss: 1 kB\nPss: 2 kB','Pss: -1 kB']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):pss_bytes(raw)

    def test_process_identity_change_cannot_be_a_memory_result(self):
        class Remote:
            replies=iter(['app.bundle\x00',self.stat(100),'Pss: 2048 kB','other.bundle\x00'])
            def hdc(self,args):return next(self.replies)
        with self.assertRaisesRegex(ValueError,'identity changed'):
            read_process(Remote(),123,'app.bundle')

    def test_same_name_restarted_process_is_rejected(self):
        class Remote:
            replies=iter(['app.bundle\x00',self.stat(100),'Pss: 2048 kB','app.bundle\x00',self.stat(200)])
            def hdc(self,args):return next(self.replies)
        with self.assertRaisesRegex(ValueError,'restarted'):
            read_process(Remote(),123,'app.bundle')

    def test_kernel_stat_handles_spaces_and_parentheses_in_process_name(self):
        self.assertEqual(start_ticks(self.stat(54321),123),54321)
        with self.assertRaises(ValueError):start_ticks(self.stat(54321),456)

    def test_window_uses_final_absolute_pss_not_peak_or_delta(self):
        before={'process_start_ticks':100,'pss_bytes':4096}
        after={'process_start_ticks':100,'pss_bytes':2048}
        with patch('system_pss.read_process',side_effect=[before,after]):
            result=capture_window(None,123,'app.bundle',lambda:None)
        self.assertEqual(result['app_pss_bytes'],2048)
        self.assertEqual([s['phase'] for s in result['snapshots']],['before','after'])

    def test_restart_between_snapshots_invalidates_trial(self):
        with patch('system_pss.read_process',side_effect=[
                {'process_start_ticks':100,'pss_bytes':4096},
                {'process_start_ticks':200,'pss_bytes':2048}]):
            with self.assertRaisesRegex(ValueError,'restarted within'):
                capture_window(None,123,'app.bundle',lambda:None)

    def test_ui_failure_is_not_a_successful_memory_trial(self):
        def workload():raise RuntimeError('normal UI failed')
        with patch('system_pss.read_process',return_value={'process_start_ticks':100,'pss_bytes':4096}):
            with self.assertRaisesRegex(RuntimeError,'normal UI failed'):
                capture_window(None,123,'app.bundle',workload)

    def test_background_observer_failure_cannot_be_swallowed(self):
        observed=threading.Event()
        calls=[]
        def read(*args):
            calls.append(1)
            if len(calls)==1:
                return {'process_start_ticks':100,'pss_bytes':4096}
            observed.set()
            raise ValueError('kernel read failed')
        def workload():
            self.assertTrue(observed.wait(2),'observer did not run')
        with patch('system_pss.read_process',side_effect=read):
            with self.assertRaisesRegex(RuntimeError,'observer failed'):
                capture_window(None,123,'app.bundle',workload,interval_s=.001)


if __name__=='__main__':unittest.main()
