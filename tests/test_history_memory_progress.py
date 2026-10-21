import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from history_memory_progress import verify
from seed_search_history import production_states


class HistoryMemoryProgressTest(unittest.TestCase):
    def test_both_production_representations_have_the_same_submission_history(self):
        events=[f'keyword {n}' for n in range(100)]
        for variant,raw in production_states(events).items():
            layout={'attributes':{'bundleName':'app'},'children':[
                {'attributes':{'text':'搜索记录'}},{'attributes':{'text':events[-1]}}]}
            result=verify(layout,raw,events,variant,'app')
            self.assertEqual(result['retained_keywords'],100 if variant=='unfixed' else 20)
            with self.assertRaises(ValueError):verify(layout,raw,events+['another'],variant,'app')
            with self.assertRaises(ValueError):verify(layout,raw,events,variant,'other.app')
            layout['children'].pop()
            with self.assertRaises(ValueError):verify(layout,raw,events,variant,'app')
