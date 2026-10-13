import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from page_lifecycle import verify_reconstructions


class PageLifecycleTest(unittest.TestCase):
    def stat(self,tick):
        return '123 (app) '+' '.join(['S']+['0']*18+[str(tick)]+['0']*4)

    def records(self):
        return [{'pid':123,'bundle':'app.bundle','raw_cmdline':'app.bundle\x00',
                 'raw_stat_before':self.stat(100),'raw_stat_after':self.stat(100),'window_id':str(w)}
                for w in [1,2,3,4,5,6,7,8,9,10,11,11]]

    def test_real_windows_in_one_process(self):
        self.assertEqual(verify_reconstructions(self.records(),'app.bundle')['reconstructions'],10)

    def test_visible_but_reused_page_is_not_reconstruction(self):
        records=self.records()
        for r in records:r['window_id']='1'
        with self.assertRaisesRegex(ValueError,'reused a window'):
            verify_reconstructions(records,'app.bundle')

    def test_process_restarts_or_wrong_app_cannot_validate_static_cache(self):
        for kind in ['restart','wrong-app','missing']:
            records=copy.deepcopy(self.records())
            if kind=='restart':
                records[5]['raw_stat_before']=self.stat(200);records[5]['raw_stat_after']=self.stat(200)
            if kind=='wrong-app':records[5]['raw_cmdline']='other.bundle\x00'
            if kind=='missing':records.pop()
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify_reconstructions(records,'app.bundle')


if __name__=='__main__':unittest.main()
