import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from native_key_events import verify_burst


class NativeKeyEventsTest(unittest.TestCase):
    word = 'electronic'

    def rows(self):
        rows=[dict(kind='registration',result=0,pid=42,window_id=7,probe=False,monotonic_ns=1000000000)]
        codes=[2017+ord(letter)-ord('a') for letter in self.word]+[2054]
        for i,code in enumerate(codes):
            for action in (1,2):
                rows.append(dict(kind='key',window_id=7,key_code=code,action=action,
                    observer_monotonic_ns=1100000000+i*50000000+action*1000000,action_time=i*50+action))
        rows.append(dict(kind='removal',result=0,monotonic_ns=3000000000))
        return rows

    def check(self,rows):return verify_burst('\n'.join(json.dumps(row) for row in rows),7,self.word,42)

    def test_full_ten_character_submit_burst_proves_only_mmi_not_app_callbacks(self):
        rows=self.rows();original=copy.deepcopy(rows);result=self.check(rows)
        self.assertEqual(result['characters'],10)
        self.assertTrue(result['submit_observed'])
        self.assertEqual(result['mmi_key_down_spacing_ms'],[50]*9)
        self.assertFalse(result['arkui_callback_spacing_verified'])
        self.assertEqual(rows,original)

    def test_missing_extra_duplicated_foreign_or_reordered_events_fail(self):
        for kind in ('missing','extra','duplicate','window','key','action','clock'):
            rows=self.rows()
            if kind=='missing':rows.pop(3)
            if kind=='extra':rows.insert(3,copy.deepcopy(rows[2]))
            if kind=='duplicate':rows[3]=copy.deepcopy(rows[1])
            if kind=='window':rows[3]['window_id']=8
            if kind=='key':rows[3]['key_code']=2054
            if kind=='action':rows[3]['action']=2
            if kind=='clock':rows[3]['observer_monotonic_ns']=rows[2]['observer_monotonic_ns']
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.check(rows)

    def test_permission_failure_probe_foreign_owner_or_failed_removal_cannot_pass(self):
        for index,key,value in ((0,'result',201),(0,'probe',True),(0,'pid',43),(-1,'result',201)):
            rows=self.rows();rows[index][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.check(rows)

    def test_observations_outside_monitor_lifetime_or_slow_letters_fail(self):
        rows=self.rows();rows[1]['observer_monotonic_ns']=999999999
        with self.assertRaises(ValueError):self.check(rows)
        rows=self.rows()
        for row in rows[3:-1]:row['observer_monotonic_ns']+=300000000
        with self.assertRaisesRegex(ValueError,'300ms'):self.check(rows)

    def test_a_pause_before_submit_is_not_mistaken_for_slow_typing(self):
        rows=self.rows()
        for row in rows[-3:-1]:row['observer_monotonic_ns']+=1000000000
        self.assertEqual(self.check(rows)['mmi_key_down_spacing_ms'],[50]*9)
