import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rss_refresh_progress import verify_observation


class ReaderRefreshProgressTest(unittest.TestCase):
    def observation(self):
        before = [{'url': f'http://127.0.0.1:18491/feeds/{i}.xml', 'last_fetched': 100}
                  for i in range(1, 11)]
        after = [dict(r, last_fetched=200) for r in before]
        return {'before': {'raw_rows': json.dumps(before), 'started_monotonic': 1, 'ended_monotonic': 2},
                'after': {'raw_rows': json.dumps(after), 'started_monotonic': 3, 'ended_monotonic': 4},
                'button_after': {'type': 'Button', 'bounds': '[195,326][296,427]',
                                 'enabled': 'true', 'bundleName': 'com.sheafreader.hm'},
                'progress': {'feeds_refreshed': 10,
                             'method': 'all existing feed last_fetched values advanced after the normal refresh action'}}

    def test_partial_fetch_cannot_claim_complete_refresh(self):
        observation = self.observation()
        self.assertEqual(verify_observation(observation)['feeds_refreshed'], 10)
        rows = json.loads(observation['after']['raw_rows'])
        rows[-1]['last_fetched'] = 100
        observation['after']['raw_rows'] = json.dumps(rows)
        with self.assertRaisesRegex(ValueError, 'not all'):
            verify_observation(observation)

    def test_updated_timestamps_before_insertion_finishes_are_insufficient(self):
        observation = self.observation()
        observation['button_after']['enabled'] = 'false'
        with self.assertRaisesRegex(ValueError, 'enabled state'):
            verify_observation(observation)

    def test_claimed_summary_and_observation_order_are_recomputed(self):
        observation = self.observation()
        changed = copy.deepcopy(observation)
        changed['progress']['feeds_refreshed'] = 100
        with self.assertRaisesRegex(ValueError, 'summary differs'):
            verify_observation(changed)
        observation['after']['started_monotonic'] = 1.5
        with self.assertRaisesRegex(ValueError, 'not sequential'):
            verify_observation(observation)


if __name__ == '__main__':
    unittest.main()
