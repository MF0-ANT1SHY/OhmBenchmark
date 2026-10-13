import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from jingmo_data_service import Catalogue
from jingmo_import_fixture import verify_state, read_state


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


if __name__ == '__main__':
    unittest.main()
