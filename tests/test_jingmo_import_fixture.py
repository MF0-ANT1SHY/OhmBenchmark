import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from jingmo_data_service import Catalogue
from jingmo_import_fixture import verify_state, read_state, verify_capture_window


class PoetryImportDataTest(unittest.TestCase):
    def test_complete_import_requires_all_business_fields(self):
        rows = Catalogue().poems
        verify_state({'raw_rows': json.dumps(rows), 'count': 5000}, True)
        bad = copy.deepcopy(rows)
        bad[-1]['content'] = 'different poem body'
        with self.assertRaises(ValueError):
            verify_state({'raw_rows': json.dumps(bad), 'count': 5000}, True)

    def test_partial_import_and_nonempty_cold_start_are_rejected(self):
        rows = Catalogue().poems[:-1]
        with self.assertRaises(ValueError):
            verify_state({'raw_rows': json.dumps(rows), 'count': 4999}, True)
        with self.assertRaises(ValueError):
            verify_state({'raw_rows': json.dumps(rows), 'count': 4999}, False)
        verify_state({'raw_rows': '', 'count': 0}, False)

    def test_device_sql_error_cannot_be_a_count(self):
        with self.assertRaises(ValueError):
            read_state(lambda command: 'Error: unable to open database')

    def test_import_observed_after_profiling_cannot_pass_capture_gate(self):
        state = {'raw_rows': json.dumps(Catalogue().poems), 'count': 5000,
                 'started_monotonic': 15, 'ended_monotonic': 16}
        verify_capture_window(state, 10, 20)
        with self.assertRaisesRegex(ValueError, 'within the measured window'):
            verify_capture_window(state, 10, 14)
        state['started_monotonic'] = 17
        with self.assertRaises(ValueError):
            verify_capture_window(state, 10, 20)


if __name__ == '__main__':
    unittest.main()
