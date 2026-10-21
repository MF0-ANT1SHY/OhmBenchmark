import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reader_refresh_latency import verify_capture
from rss_refresh_progress import REFRESH_BUTTON


def state(start, fetched):
    return {'started_monotonic': start, 'ended_monotonic': start + .1,
            'raw_rows': json.dumps([{'url': f'http://127.0.0.1:18491/feeds/{i}.xml',
                                    'last_fetched': fetched} for i in range(1, 11)])}


class RefreshLatencyTests(unittest.TestCase):
    def setUp(self):
        self.record = {'status': 'CAPTURED', 'start': 100, 'key_returned': 101, 'end': 117,
                       'pid_before': '123', 'pid_after': '123', 'before': state(99, 10),
                       'after': state(118, 11), 'observations': [state(102, 10), state(116, 11)],
                       'button_after': {**REFRESH_BUTTON, 'enabled': 'true', 'bundleName': 'com.sheafreader.hm'},
                       'requests': [{'path': f'/feeds/{i + 1}.xml', 'start': 101 + i * 1.5,
                                     'end': 102.5 + i * 1.5} for i in range(10)]}

    def test_conservative_bounds(self):
        result = verify_capture(self.record, 1.5)
        self.assertEqual(result['elapsed_lower_s'], 1)
        self.assertEqual(result['elapsed_upper_s'], 17)

    def test_missing_work_or_changed_process_rejected(self):
        for key, value in [('requests', self.record['requests'][:-1]), ('pid_after', '999'),
                           ('observations', [state(116, 11)]), ('before', state(100, 10))]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_capture({**self.record, key: value}, 1.5)

    def test_network_condition_not_met(self):
        record = copy.deepcopy(self.record)
        record['requests'][0]['end'] = record['requests'][0]['start'] + .1
        with self.assertRaises(ValueError):
            verify_capture(record, 1.5)

    def test_ordinary_favicon_does_not_count_as_feed(self):
        self.record['requests'].append({'path': '/favicon.ico', 'start': 101, 'end': 101.1})
        self.assertEqual(verify_capture(self.record, 1.5)['feeds_refreshed'], 10)
        self.record['requests'].append({'path': '/feeds/11.xml', 'start': 101, 'end': 103})
        with self.assertRaises(ValueError):
            verify_capture(self.record, 1.5)
