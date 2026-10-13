import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rss_dataset import normalize
from rss_data_service import Catalogue


class OrdinaryRSSDatasetTest(unittest.TestCase):
    def test_default_retains_original_article_payload(self):
        self.assertEqual(normalize(), {'body_bytes': 32768})
        original = Catalogue('http://127.0.0.1:18491')
        declared = Catalogue('http://127.0.0.1:18491', **normalize())
        self.assertEqual(original.feed(1), declared.feed(1))

    def test_invalid_sizes_and_non_data_switches_are_rejected(self):
        for size in (0, -1, True, '256', 40001):
            with self.subTest(size=size), self.assertRaises(ValueError):
                normalize({'body_bytes': size})
        with self.assertRaises(ValueError):
            normalize({'body_bytes': 256, 'skip_work': True})

    def test_largest_declared_feed_fits_native_default_http_limit(self):
        data = Catalogue('http://127.0.0.1:18491', **normalize({'body_bytes': 40000}))
        self.assertLess(len(data.feed(10)), 5 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
