import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from browser_visit_progress import verify_progress, verify_capture


def state(records, start, end):
    return {'raw_tables':json.dumps([{'name':'history_2026_10_15'}]),'raw_rows':json.dumps(records),
            'started_monotonic':start,'ended_monotonic':end}


class BrowserVisitProgressTest(unittest.TestCase):
    def setUp(self):
        self.before=state([],1,2)
        self.records=[{'history_table':'history_2026_10_15','id':i,'title':'Example Domain',
                       'url':'https://example.com/','timestamp':'2026_10_15 09:30'} for i in range(1,16)]
        self.after=state(self.records,4,5)

    def test_fifteen_normal_rows_and_native_capture_window(self):
        progress=verify_progress(self.before,self.after)
        self.assertEqual(progress['saved_visits'],15)
        verify_capture({'before':self.before,'after':self.after,'progress':progress},3,6)

    def test_missing_extra_wrong_title_or_wrong_day_navigations_rejected(self):
        for kind in ('missing','extra','wrong-title','wrong-day'):
            rows=copy.deepcopy(self.records)
            if kind=='missing':rows.pop()
            if kind=='extra':rows.append({**rows[0],'id':16})
            if kind=='wrong-title':rows[0]['title']='Network error'
            if kind=='wrong-day':rows[0]['timestamp']='2026_10_14 09:30'
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify_progress(self.before,state(rows,4,5))

    def test_preexisting_rows_cannot_be_overwritten_to_fake_new_visits(self):
        before=state(self.records[:1],1,2)
        with self.assertRaises(ValueError):verify_progress(before,self.after)
        altered=copy.deepcopy(self.records);altered[0]['url']='https://another.example/'
        with self.assertRaises(ValueError):verify_progress(before,state(altered,4,5))

    def test_async_completion_outside_the_capture_or_forged_summary_rejected(self):
        observation={'before':self.before,'after':self.after,'progress':verify_progress(self.before,self.after)}
        with self.assertRaises(ValueError):verify_capture(observation,3,4.5)
        observation['progress']['saved_visits']=16
        with self.assertRaises(ValueError):verify_capture(observation,3,6)
