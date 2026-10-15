"""Validate existing native WebPage callbacks; no instrumentation in the app."""
from decimal import Decimal
import re

from system_pss import start_ticks

URL = 'https://www.wanandroid.com/blog/show/3942'
TITLE = 'Android 技术周刊 （2026-10-07 ~ 2026-10-14）'
CASE = 'wanharmony_web_progress_log_storm'


def read_state(shell, directory, label):
    from native_hilog import snapshot
    from wan_history_progress import BUNDLE, PREFERENCES
    pid = shell('pidof '+BUNDLE).strip()
    if not pid.isdigit():
        raise ValueError('one live Wan process is required')
    pid = int(pid)
    stat = shell(f'cat /proc/{pid}/stat')
    if shell(f'cat /proc/{pid}/cmdline').split('\x00', 1)[0].strip() != BUNDLE:
        raise ValueError('web observation targets a different app')
    result = snapshot(pid, directory, label)
    result['raw_stat'] = stat
    result['raw_xml'] = shell('cat '+PREFERENCES)
    if start_ticks(stat, pid) != start_ticks(shell(f'cat /proc/{pid}/stat'), pid):
        raise ValueError('web observation process changed')
    return result


def verify_fixture(preparation, observation):
    from pathlib import Path
    import json
    from install_wanharmony_history_fixture import fixture_state, verify_deployment
    from wan_history_progress import history, PREFERENCES
    folder = Path(preparation['fixture_dir'])
    fixture, _ = fixture_state(folder)
    entries = json.loads((folder/'history.json').read_text())
    if (not preparation.get('installation_verified') or preparation['preferences'] != PREFERENCES or
            len(entries) != 1 or entries[0]['url'] != URL or
            preparation['sha256'] != fixture['fixture_sha256'] or
            verify_deployment(preparation, entries, fixture) != preparation['deployed_sha256']):
        raise ValueError('same ordinary one-page history input is not proven')
    for state in (observation['before'], observation['after']):
        current = history(state)
        if len(current) != 1 or current[0]['url'] != URL or current[0]['sticky'] is not False:
            raise ValueError('native single-page history changed beyond normal title/time updates')
    return fixture['fixture_sha256']


def verify_capture(observation, start, end, pids, directory):
    import hashlib
    from pathlib import Path
    if (pids != [observation['pid']] or observation['actions_start_monotonic'] != start or
            observation['after']['ended_monotonic'] > end):
        raise ValueError('normal refreshes were not observed within the CPU window')
    for label in ('before', 'after'):
        state = observation[label]
        for stream in ('stdout', 'stderr'):
            raw = (Path(directory)/'native-logs'/(label+'.'+stream+'.bin')).read_bytes()
            key = 'raw_sha256' if stream == 'stdout' else 'stderr_sha256'
            if hashlib.sha256(raw).hexdigest() != state[key]:
                raise ValueError('native HiLog stream differs from its original bytes')
            if stream == 'stdout' and raw.decode('utf-8', errors='replace') != state['raw_logs']:
                raise ValueError('decoded callbacks differ from the original native HiLog stream')
    progress = verify(observation)
    if observation.get('progress') != progress:
        raise ValueError('refresh summary differs from native callback evidence')
    return progress


def callbacks(snapshot):
    rows = []
    for line in snapshot['raw_logs'].splitlines():
        match = re.match(r'^\s*(\d+\.\d{9})\s+(\d+)\s+\d+\s+[DIWEF]\s+'
                         r'\S*org\.example\.wan\.ohos/WebPage:\s+(.*)$', line)
        if not match:
            continue
        stamp, pid, message = match.groups()
        if int(pid) != snapshot['pid']:
            raise ValueError('WebPage callback belongs to a different process')
        for kind, prefix in (('begin', 'onPageBegin url: '), ('end', 'onPageEnd url: '),
                             ('title', 'onTitleReceive title: '), ('error', 'onErrorReceive url: '),
                             ('progress', 'onProgressChange progress: ')):
            if message.startswith(prefix):
                rows.append((int(Decimal(stamp)*1000000000), kind, message[len(prefix):], line))
                break
    if len({row[3] for row in rows}) != len(rows) or any(a[0] > b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('duplicate or out-of-order native WebPage callbacks')
    return rows


def completed_pages(rows, expected):
    pages = []
    active = None
    pending_progress = []
    for stamp, kind, value, _ in rows:
        if kind == 'error':
            raise ValueError('native page or subresource errors invalidate the workload')
        if kind == 'begin':
            if active and ('end_ns' not in active or not active.get('title')):
                raise ValueError('overlapping or incomplete native page loads')
            if value != URL:
                raise ValueError('unrelated page load or redirect')
            active = {'url': value, 'begin_ns': stamp, 'progress': pending_progress}
            pending_progress = []
            pages.append(active)
        elif kind == 'end':
            if not active or value != URL or 'end_ns' in active:
                raise ValueError('page end does not match one normal load')
            active['end_ns'] = stamp
        elif kind == 'title':
            if not active or not value.strip():
                raise ValueError('title without an unambiguous normal load')
            active['title'] = value
        elif kind == 'progress':
            if not re.fullmatch(r'\d{1,3}', value) or not 0 <= int(value) <= 100:
                raise ValueError('invalid existing native progress log')
            # ArkWeb emits initial low progress before onPageBegin and can
            # emit repeated 100 after onPageEnd. Preserve both actual orders;
            # unfinished low-progress callbacks require a subsequent begin.
            if not active or pending_progress or ('end_ns' in active and int(value) < 100):
                pending_progress.append(int(value))
            else:
                active['progress'].append(int(value))
    if pending_progress or len(pages) != expected or any('end_ns' not in p or not p.get('title') for p in pages):
        raise ValueError('all five normal completed page loads are not proven')
    return pages


def verify(observation):
    before, after = observation['before'], observation['after']
    pid = observation['pid']
    if (type(pid) is not int or before['pid'] != pid or after['pid'] != pid or
            start_ticks(observation['stat_before'], pid) != start_ticks(observation['stat_after'], pid) or
            not 0 < before['ended_monotonic'] <= observation['actions_start_monotonic'] <
            observation['actions_end_monotonic'] < after['started_monotonic']):
        raise ValueError('callbacks do not bracket ordered actions in one process')
    old = callbacks(before)
    # The setup's latest load must itself have finished successfully.
    beginnings = [i for i, row in enumerate(old) if row[1] == 'begin']
    if not beginnings:
        raise ValueError('normal initial page load is not proven')
    completed_pages(old[beginnings[-1]:], 1)
    old_lines = {row[3] for row in old}
    pages = completed_pages([row for row in callbacks(after) if row[3] not in old_lines], 5)
    return {'completed_refreshes': 5, 'url': URL,
            'progress_logs_per_load': [len(p['progress']) for p in pages],
            'progress_values_per_load': [p['progress'] for p in pages],
            'native_page_durations_ms': [(p['end_ns']-p['begin_ns'])/1e6 for p in pages],
            'app_injection': False, 'performance_accepted': False,
            'method': 'existing native begin/end/title/progress logs; all native error callbacks rejected'}
