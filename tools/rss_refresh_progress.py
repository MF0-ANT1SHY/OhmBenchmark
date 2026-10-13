"""Observe existing reader fetch timestamps; never create app-side counters."""
import json
import time

DATABASE = '/data/app/el2/100/database/com.sheafreader.hm/entry/rdb/sheaf_reader.db'


def read_state(shell):
    started = time.monotonic()
    raw = shell(f"sqlite3 -json {DATABASE} 'SELECT url,last_fetched FROM feeds ORDER BY url;'")
    return {'raw_rows': raw, 'started_monotonic': started,
            'ended_monotonic': time.monotonic()}


def rows(state):
    if not (0 < state['started_monotonic'] <= state['ended_monotonic']):
        raise ValueError('invalid fetch-state observation window')
    data = json.loads(state['raw_rows'])
    urls = {f'http://127.0.0.1:18491/feeds/{i}.xml' for i in range(1, 11)}
    if (not isinstance(data, list) or len(data) != 10
            or {r['url'] for r in data} != urls):
        raise ValueError('fetch-state data contains missing or unrelated subscriptions')
    result = {}
    for row in data:
        value = row['last_fetched']
        if type(value) is not int or value <= 0:
            raise ValueError('fetch timestamp is not a positive ordinary database value')
        result[row['url']] = value
    return result


def verify_refresh(before, after):
    first, last = rows(before), rows(after)
    if before['ended_monotonic'] >= after['started_monotonic']:
        raise ValueError('fetch observations are not sequential')
    if any(last[url] <= first[url] for url in first):
        raise ValueError('not all normal feed fetch timestamps advanced')
    return {'feeds_refreshed': 10,
            'method': 'all existing feed last_fetched values advanced after the normal refresh action'}


REFRESH_BUTTON = {'type': 'Button', 'bounds': '[195,326][296,427]', 'match': 'exact'}


def complete_refresh(ui, before, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        after = read_state(ui.shell)
        try:
            verify_refresh(before, after)
            break
        except ValueError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    # last_fetched is written before the article insertion loop finishes. The
    # ordinary header button only becomes enabled after refreshData completes.
    button = ui.find(REFRESH_BUTTON, timeout)
    after = read_state(ui.shell)
    return {'before': before, 'after': after, 'button_after': button,
            'progress': verify_refresh(before, after)}


def verify_observation(observation):
    progress = verify_refresh(observation['before'], observation['after'])
    button = observation['button_after']
    if (button.get('type') != 'Button' or button.get('bounds') != REFRESH_BUTTON['bounds']
            or button.get('enabled') != 'true' or button.get('bundleName') != 'com.sheafreader.hm'):
        raise ValueError('ordinary refresh button did not return to its enabled state')
    if observation.get('progress') != progress:
        raise ValueError('refresh summary differs from raw database observations')
    return progress
