import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from jingmo_data_service import Catalogue
from jingmo_sync_fixture import identity, verify_preparation


class CachedPoetryDataTest(unittest.TestCase):
    def receipts(self):
        state = {'raw_rows': json.dumps(Catalogue().poems), 'count': 5000}
        source = {'sha256': 'data', 'source_sha256': 'source', 'base_url': 'url',
                  'service_pid': 12, 'service_start_ticks': 100}
        digest = identity('database', 'data')
        return ({'before': state, 'database_sha256': 'database', 'service': source, 'sha256': digest},
                {'after': copy.deepcopy(state), 'service': dict(source), 'sha256': digest})

    def test_repeat_sync_requires_complete_cached_input(self):
        before, after = self.receipts()
        verify_preparation(before, after)
        before['before'] = {'raw_rows': '', 'count': 0}
        with self.assertRaises(ValueError):
            verify_preparation(before, after)

    def test_same_row_count_with_changed_data_is_not_preservation(self):
        before, after = self.receipts()
        rows = json.loads(after['after']['raw_rows'])
        rows[-1]['writer'] = 'different author'
        after['after']['raw_rows'] = json.dumps(rows)
        with self.assertRaises(ValueError):
            verify_preparation(before, after)

    def test_service_restart_does_not_prove_same_input_lifetime(self):
        before, after = self.receipts()
        after['service']['service_start_ticks'] += 1
        with self.assertRaises(ValueError):
            verify_preparation(before, after)


if __name__ == '__main__':
    unittest.main()
