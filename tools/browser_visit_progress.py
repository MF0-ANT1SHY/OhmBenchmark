"""Observe ordinary saved browsing records, never application-side counters."""
import json
import re
import shlex
import time

CASE = 'browser_insert_date_lookup_cache'
DATABASE = '/data/app/el2/100/database/com.example.nanvision/entry/rdb/Histories.db'
URLS = {'https://example.com', 'https://example.com/'}


def read_state(shell):
    started = time.monotonic()
    table_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'history_%' ORDER BY name;"
    raw_tables = shell(f'sqlite3 -json {DATABASE} {shlex.quote(table_sql)}').strip() or '[]'
    tables = [row['name'] for row in json.loads(raw_tables)]
    if any(not re.fullmatch(r'history_[0-9]{4}_[0-9]{2}_[0-9]{2}', name) for name in tables):
        raise ValueError('unexpected ordinary history table name')
    queries = [f"SELECT '{name}' AS history_table,id,title,url,timestamp FROM {name}" for name in tables]
    raw_rows = (shell(f'sqlite3 -json {DATABASE} {shlex.quote(" UNION ALL ".join(queries)+";")}').strip() or '[]') if queries else '[]'
    return {'raw_tables': raw_tables, 'raw_rows': raw_rows,
            'started_monotonic': started, 'ended_monotonic': time.monotonic()}


def rows(state):
    if not 0 < state['started_monotonic'] <= state['ended_monotonic']:
        raise ValueError('invalid ordinary history observation timestamps')
    tables = [row['name'] for row in json.loads(state['raw_tables'])]
    if len(tables) != len(set(tables)) or any(not re.fullmatch(r'history_[0-9]{4}_[0-9]{2}_[0-9]{2}', name) for name in tables):
        raise ValueError('invalid or duplicate ordinary history tables')
    records = json.loads(state['raw_rows'])
    if not isinstance(records, list):
        raise ValueError('ordinary history rows must be an array')
    result = {}
    for record in records:
        if (not isinstance(record, dict) or set(record) != {'history_table', 'id', 'title', 'url', 'timestamp'}
                or record['history_table'] not in tables or type(record['id']) is not int or record['id'] <= 0
                or any(not isinstance(record[field], str) for field in ('title', 'url', 'timestamp'))):
            raise ValueError('invalid ordinary browser history row')
        key = (record['history_table'], record['id'])
        if key in result:
            raise ValueError('duplicate ordinary browsing record')
        result[key] = record
    return result


def verify_progress(before, after):
    initial, final = rows(before), rows(after)
    if before['ended_monotonic'] >= after['started_monotonic']:
        raise ValueError('ordinary history observations are not sequential')
    if any(final.get(key) != value for key, value in initial.items()):
        raise ValueError('existing ordinary browsing records were altered or deleted')
    added = [record for key, record in final.items() if key not in initial and record['url'] in URLS]
    if len(added) != 15 or len({record['history_table'] for record in added}) != 1:
        raise ValueError('fifteen complete same-day navigations were not saved')
    for record in added:
        date = record['history_table'].removeprefix('history_')
        if record['title'] != 'Example Domain' or not re.fullmatch(re.escape(date)+r' [0-9]{2}:[0-9]{2}', record['timestamp']):
            raise ValueError('saved navigation title or timestamp differs from normal page data')
    return {'saved_visits': 15, 'history_table': added[0]['history_table'],
            'method': 'ordinary same-day Example Domain rows appended through normal browser navigation'}


def complete_visits(ui, before, timeout=120):
    deadline = time.monotonic()+timeout
    while True:
        after = read_state(ui.shell)
        try:
            progress = verify_progress(before, after)
            return {'before': before, 'after': after, 'progress': progress}
        except ValueError as exc:
            if time.monotonic() >= deadline:
                exc.observation = {'before': before, 'after': after}
                raise
            time.sleep(.5)


def verify_observation(observation):
    progress = verify_progress(observation['before'], observation['after'])
    if progress != observation.get('progress'):
        raise ValueError('saved-navigation summary differs from raw ordinary database rows')
    return progress


def verify_capture(observation, start, end):
    verify_observation(observation)
    if (not 0 < start < end or observation['before']['ended_monotonic'] > start
            or observation['after']['started_monotonic'] < start
            or observation['after']['ended_monotonic'] > end):
        raise ValueError('saved navigation completion was not observed within the CPU capture')
