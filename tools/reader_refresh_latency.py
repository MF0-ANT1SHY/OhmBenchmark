"""Recompute refresh timing bounds from external native observations."""
import math
from rss_refresh_progress import rows, verify_refresh, REFRESH_BUTTON


def verify_capture(record, response_delay_s):
    if record.get('status') != 'CAPTURED':
        raise ValueError('refresh capture is incomplete')
    start, key_end, end = (record[k] for k in ('start', 'key_returned', 'end'))
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, key_end, end)) or not 0 < start <= key_end < end:
        raise ValueError('invalid refresh action timing')
    if not record['pid_before'] or record['pid_before'] != record['pid_after']:
        raise ValueError('app process changed during refresh')
    before = record['before']; baseline = rows(before)
    if before['ended_monotonic'] >= start:
        raise ValueError('baseline overlaps the measured action')
    previous = key_end; last_incomplete = None; completed = False
    for state in record['observations']:
        current = rows(state)
        if completed or not previous <= state['started_monotonic'] <= state['ended_monotonic'] <= end:
            raise ValueError('invalid native observation sequence')
        completed = all(current[url] > baseline[url] for url in baseline)
        if not completed:
            last_incomplete = state['started_monotonic']
        previous = state['ended_monotonic']
    if not completed or last_incomplete is None:
        raise ValueError('refresh completion must be bracketed by native observations')
    verify_refresh(before, record['after'])
    button = record['button_after']
    if (button.get('enabled') != 'true' or button.get('bundleName') != 'com.sheafreader.hm'
            or button.get('bounds') != REFRESH_BUTTON['bounds'] or button.get('type') != 'Button'):
        raise ValueError('normal refresh UI did not finish')
    all_requests = record['requests']
    requests = [r for r in all_requests if r['path'] != '/favicon.ico']
    expected = {f'/feeds/{i}.xml' for i in range(1, 11)}
    if len(requests) != 10 or {r['path'] for r in requests} != expected:
        raise ValueError('refresh did not fetch exactly the ten ordinary subscriptions')
    for request in all_requests:
        if not start <= request['start'] < request['end'] <= end:
            raise ValueError('RSS request falls outside measured refresh')
        if request['path'] != '/favicon.ico' and request['end'] - request['start'] < response_delay_s:
            raise ValueError('declared network condition was not applied')
    # Actual start occurs no later than key return. At last incomplete query
    # start the refresh was not complete. This gives a conservative lower bound.
    lower = last_incomplete - key_end
    if lower <= 0:
        raise ValueError('no positive conservative latency bound')
    return {'elapsed_upper_s': end - start, 'elapsed_lower_s': lower,
            'feeds_refreshed': 10, 'method': 'normal app launch to all-feed native completion and enabled refresh UI'}
