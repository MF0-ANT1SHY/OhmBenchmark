"""Validate evaluator-only MMI key observations, not app callback timings."""
import json
import re


def verify_burst(raw, window_id, word, observer_pid, submit=True):
    if (type(window_id) is not int or window_id < 0 or
            type(observer_pid) is not int or observer_pid <= 0 or
            not isinstance(word, str) or not re.fullmatch('[a-z]{1,100}', word)):
        raise ValueError('invalid expected keyboard burst identity')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows) < 2:
        raise ValueError('monitor registration and removal are required')
    start, end = rows[0], rows[-1]
    if (start.get('kind') != 'registration' or start.get('result') != 0 or
            start.get('pid') != observer_pid or start.get('window_id') != window_id or
            start.get('probe') is not False or end.get('kind') != 'removal' or end.get('result') != 0):
        raise ValueError('key monitor ownership or cleanup is not proven')
    lower, upper = start['monotonic_ns'], end['monotonic_ns']
    if type(lower) is not int or type(upper) is not int or not 0 < lower < upper:
        raise ValueError('invalid native monitor clock bounds')
    codes = [2017 + ord(letter)-ord('a') for letter in word] + ([2054] if submit else [])
    events = rows[1:-1]
    if len(events) != len(codes)*2:
        raise ValueError('missing or extra native key events')
    stamps = []
    for index, event in enumerate(events):
        stamp = event.get('observer_monotonic_ns')
        if (event.get('kind') != 'key' or event.get('window_id') != window_id or
                event.get('key_code') != codes[index//2] or event.get('action') != (1 if index%2 == 0 else 2) or
                type(stamp) is not int or not lower < stamp < upper):
            raise ValueError('key order, target, action or clock does not match the burst')
        stamps.append(stamp)
    if any(a >= b for a,b in zip(stamps,stamps[1:])):
        raise ValueError('native key observations are not strictly ordered')
    downs = stamps[::2][:len(word)]
    gaps = [(b-a)/1000000 for a,b in zip(downs,downs[1:])]
    if any(gap >= 300 for gap in gaps):
        raise ValueError('native typing did not stay inside the 300ms debounce interval')
    return {'characters':len(word), 'submit_observed':submit, 'window_id':window_id,
            'mmi_key_down_spacing_ms':gaps, 'all_adjacent_letters_under_300ms':True,
            'arkui_callback_spacing_verified':False,
            'method':'separate native OH_Input key monitor; not app instrumentation'}
