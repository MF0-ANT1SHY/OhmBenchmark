import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from interview_history_progress import keywords,empty_preferences,verify_observation,BUNDLE

class HistoryPersistenceTest(unittest.TestCase):
    def state(self,raw,start):
        stat='20 (app) S '+' '.join(['0']*18+['123']+['0']*10)
        return dict(pid=20,raw_stat=stat,raw_stat_after=stat,raw_cmdline=BUNDLE,raw_preferences=raw,started_monotonic=start,ended_monotonic=start+.1)
    def test_exact_empty_to_submitted_state_not_flush_count(self):
        before=self.state('<preferences />',1);after=self.state('<preferences><string key="a">a</string><string key="b">b</string></preferences>',2)
        result=verify_observation(before,after,['b','a']);self.assertEqual(result['persisted_keywords'],2)
        self.assertFalse(result['individual_flush_count_verified'])
        for expected in (['a'],['a','b','c']):
            with self.assertRaises(ValueError):verify_observation(before,after,expected)
        stale=copy.deepcopy(before);stale['raw_preferences']='<preferences><string key="a">a</string></preferences>'
        with self.assertRaises(ValueError):verify_observation(stale,after,['a','b'])
    def test_only_dedicated_native_string_history_may_be_emptied(self):
        raw='<preferences><string key="a">a</string></preferences>'
        self.assertEqual(keywords(empty_preferences(raw)),[])
        for raw in ('<preferences><int key="counter" value="1" /></preferences>','<preferences><string key="a">other</string></preferences>','<preferences><string key="a">a</string><string key="a">a</string></preferences>'):
            with self.assertRaises(ValueError):empty_preferences(raw)
    def test_foreign_process_or_overlapping_observation_fails(self):
        before=self.state('<preferences />',1);after=self.state('<preferences><string key="a">a</string></preferences>',1)
        with self.assertRaises(ValueError):verify_observation(before,after,['a'])
        after['started_monotonic']=2;after['ended_monotonic']=3;after['raw_cmdline']='foreign'
        with self.assertRaises(ValueError):verify_observation(before,after,['a'])

    def test_native_version_attribute_is_preserved_and_unknown_formats_rejected(self):
        import xml.etree.ElementTree as ET
        native='<preferences version="1.0"><string key="a">a</string></preferences>'
        empty=empty_preferences(native)
        self.assertEqual(ET.fromstring(empty).attrib,{'version':'1.0'})
        self.assertEqual(keywords(empty),[])
        for attrs in ('version="2.0"','other="value"','version="1.0" other="value"'):
            with self.assertRaises(ValueError):empty_preferences('<preferences '+attrs+' />')
