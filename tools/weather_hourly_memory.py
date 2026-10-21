"""Validate successful complete hourly forecasts from ordinary HTTP receipts."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from weather_hourly_data_service import CITIES, response


def verify_requests(record, count):
    counts = Counter()
    for row in record['requests']:
        if not record['action_start_monotonic'] <= row['start'] <= row['end'] <= record['action_end_monotonic']:
            raise ValueError('hourly request outside ordinary measured work')
        status, body = response(row['path'], row['retrieved_at'])
        if (status != 200 or row['status'] != 200 or row['error'] is not None
                or row['body_bytes'] != len(body) or row['sent_bytes'] != len(body)
                or row['body_sha256'] != hashlib.sha256(body).hexdigest()):
            raise ValueError('hourly forecast response incomplete or changed')
        counts[parse_qs(urlsplit(row['path']).query)['city'][0]] += 1
    if dict(counts) != {city: count for city in CITIES}:
        raise ValueError('complete declared ten-city hourly refreshes required')
    return dict(counts)


def _verify_capture(record, folder, revision, metric, count):
    """Recheck original screen evidence; this function never accepts a case."""
    from system_pss import verify_window
    from weather_icon_pixels import icon_boxes
    from weather_session_gc_memory import verify_gc_receipts
    from weather_session_memory import BUNDLE
    if (record.get('status') != 'CAPTURED'
            or record.get('measurement_revision') != revision
            or record.get('metric') != metric
            or record.get('performance_accepted') is not False
            or record.get('gc_completion_claimed') is not False):
        raise ValueError('not an original hourly diagnostic screen')
    if record['measured_returns'] != count or record['warmup_count'] != 10:
        raise ValueError('hourly screen workload changed')
    verify_window(record, BUNDLE)
    bounds = verify_gc_receipts(record)
    if bounds != record['growth_bounds']:
        raise ValueError('hourly growth summary differs from kernel totals')
    verify_requests(record, count)
    if len(record['steps']) != count:
        raise ValueError('hourly native refresh steps incomplete')
    for index, step in enumerate(record['steps'], 1):
        if step['number'] != index:
            raise ValueError('hourly native refresh order changed')
        icon_boxes(step['layout'])
    icon_boxes(record['initial_layout'])
    icon_boxes(record['final_layout'])
    folder = Path(folder)
    if hashlib.sha256((folder / 'plan.json').read_bytes()).hexdigest() != record['plan_sha256']:
        raise ValueError('hourly screen plan differs')
    plan = json.loads((folder / 'plan.json').read_text())
    if (plan['bundle'] != BUNDLE or plan['measured'][0]['count'] != count
            or plan['setup'][-2]['op'] != 'repeat' or plan['setup'][-2]['count'] != 10):
        raise ValueError('hourly screen plan count or process differs')
    fixture = record['fixture_before']
    if fixture != record['fixture_after'] or fixture != json.loads((folder / 'fixture-before.json').read_text()):
        raise ValueError('hourly fixture identity changed')
    root = Path(__file__).resolve().parent
    for key, source in (('source', 'weather_hourly_data_service.py'),
                        ('launcher', 'weather_hourly_workstation_lease.py'),
                        ('daily', 'weather_session_data_service.py')):
        if hashlib.sha256((root / source).read_bytes()).hexdigest() != fixture[key + '_sha256']:
            raise ValueError('hourly fixture source differs: ' + key)
    return bounds


def verify_screen(record, folder):
    return _verify_capture(record, folder, 'hourly-gc-screen-v1',
                           'diagnostic_gc_requested_pss_growth_bytes', 20)


def frozen_contract():
    path = Path(__file__).resolve().parents[1] / 'validation/weather-hourly-gc-growth-v7-contract.json'
    contract = json.loads(path.read_text())
    expected = {'case': 'weatherassistant_http_session_leak',
                'measurement_revision': 'gc-growth-v7',
                'metric': 'app_gc_requested_pss_growth_bytes',
                'candidate_revision': 'weather-hourly-v5',
                'cities': 10, 'forecast_horizon_hours': 168,
                'warmup_returns': 10, 'measured_returns': 40,
                'required_successful_forecasts_per_trial': 400,
                'kernel_samples_per_boundary_window': 3, 'paired_rounds': 3,
                'required_ratio_each_pair_and_median': 3.0,
                'fixed_growth_denominator_floor_bytes': 1048576,
                'minimum_unfixed_lower_growth_bytes': 5242880,
                'minimum_excess_growth_bytes': 5242880,
                'native_gc_requests_per_trial': 2,
                'settle_seconds_after_each_gc_request': 10,
                'gc_completion_claimed': False, 'app_injection': False,
                'performance_accepted': False}
    if any(contract.get(k) != v for k, v in expected.items()):
        raise ValueError('frozen hourly large-gap contract changed')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_capture(record, folder):
    if record.get('contract_sha256') != frozen_contract():
        raise ValueError('hourly prospective contract differs from capture')
    return _verify_capture(record, folder, 'gc-growth-v7',
                           'app_gc_requested_pss_growth_bytes', 40)
