import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from measurement_paths import capture_root


class MeasurementPathsTest(unittest.TestCase):
    def test_original_paths_remain_unchanged(self):
        self.assertEqual(capture_root(Path('/a'),{},'app_pss_bytes'),Path('/a/pss-captures'))

    def test_revision_does_not_overwrite_original_trials(self):
        self.assertEqual(capture_root(Path('/a'),{'measurement_revision':'history-10000-v2'},'app_pss_bytes'),
                         Path('/a/pss-captures/history-10000-v2'))

    def test_revision_cannot_escape_case_directory(self):
        for value in ('../old','/tmp/out','','a/b',42):
            with self.subTest(value=value), self.assertRaises(ValueError):
                capture_root(Path('/a'),{'measurement_revision':value},'app_pss_bytes')
