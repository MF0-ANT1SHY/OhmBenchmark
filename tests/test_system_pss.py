import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from system_pss import pss_bytes,read_process,start_ticks


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


if __name__=='__main__':unittest.main()
