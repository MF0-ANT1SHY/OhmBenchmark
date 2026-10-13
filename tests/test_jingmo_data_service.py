import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from jingmo_data_service import Catalogue
from seed_classic_poems import generate


class OrdinaryPoetryProtocolTest(unittest.TestCase):
    def test_poetry_fields_match_existing_ordinary_database_fixture(self):
        catalogue = Catalogue(3)
        with tempfile.TemporaryDirectory() as folder:
            database = generate(Path(folder)/'poems.db', 3)
            with sqlite3.connect(database) as db:
                db.row_factory = sqlite3.Row
                rows = [dict(r) for r in db.execute('SELECT * FROM classicalliterature_classicpoem ORDER BY id')]
        self.assertEqual(rows, catalogue.poems)
        response = json.loads(catalogue.response('/api/classicalliterature_classicpoem1.json'))
        self.assertEqual(response, {'total': 3, 'data': rows, 'next_page': None})

    def test_dataset_metadata_describes_the_same_business_records(self):
        catalogue = Catalogue(7)
        metadata = json.loads(catalogue.response('/api/dataset_v2.json'))
        self.assertEqual(metadata[0]['count'], len(catalogue.poems))

    def test_unknown_and_evaluator_paths_are_not_endpoints(self):
        catalogue = Catalogue(1)
        for route in ('/status', '/counter', '/diag', '/reset', '/api/unknown.json'):
            with self.subTest(route=route), self.assertRaises(KeyError):
                catalogue.response(route)


if __name__ == '__main__':
    unittest.main()
