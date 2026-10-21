import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from weather_hourly_data_service import CITIES, response
from weather_hourly_memory import verify_requests


def record():
    rows = []
    for city in CITIES:
        path = '/v3/weather/weatherInfo?city=' + city + '&extensions=all'
        timestamp = '2026-10-21T00:00:00+00:00'
        status, body = response(path, timestamp)
        rows.append(dict(path=path, retrieved_at=timestamp, status=status, error=None,
                         start=2, end=3, body_bytes=len(body), sent_bytes=len(body),
                         body_sha256=hashlib.sha256(body).hexdigest()))
    return dict(action_start_monotonic=1, action_end_monotonic=4, requests=rows)


class HourlyReceiptTests(unittest.TestCase):
    def test_complete_ten_city_refresh(self):
        self.assertEqual(verify_requests(record(), 1), {city: 1 for city in CITIES})

    def test_modified_timestamp_partial_transfer_and_late_response_rejected(self):
        original = record()
        for field, value in [('retrieved_at', '2026-10-21T01:00:00+00:00'),
                             ('sent_bytes', 1), ('end', 5), ('status', 500)]:
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed['requests'][0][field] = value
                with self.assertRaises(ValueError):
                    verify_requests(changed, 1)

    def test_missing_or_duplicate_city_rejected(self):
        changed = record()
        changed['requests'][-1] = changed['requests'][0]
        with self.assertRaisesRegex(ValueError, 'ten-city'):
            verify_requests(changed, 1)


class FrozenHourlyContractTests(unittest.TestCase):
    def test_lowered_gate_or_shorter_gc_wait_rejected_with_matching_hash(self):
        import weather_hourly_memory as module
        original = Path(module.__file__).resolve().parents[1] / 'validation/weather-hourly-gc-growth-v7-contract.json'
        for key, value in [('required_ratio_each_pair_and_median', 2.0),
                           ('minimum_excess_growth_bytes', 1048576),
                           ('settle_seconds_after_each_gc_request', 0),
                           ('measured_returns', 20)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                (base / 'validation').mkdir()
                contract = json.loads(original.read_text())
                contract[key] = value
                path = base / 'validation' / original.name
                path.write_text(json.dumps(contract))
                evidence = {'contract_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                with patch.object(module, '__file__', str(base / 'tools/weather_hourly_memory.py')):
                    with self.assertRaisesRegex(ValueError, 'frozen hourly large-gap contract changed'):
                        module.verify_capture(evidence, base)
