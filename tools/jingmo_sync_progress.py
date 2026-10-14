"""Observe existing business completion logs outside the application."""
import re
import time
from decimal import Decimal

EXPRESSION = 'classic poem dataset size:|Batch insert is |dataset already imported'


def read_state(shell):
    started = time.monotonic()
    pid = shell('pidof com.hefengbao.jingmo.hw').strip()
    if not pid.isdigit():
        raise ValueError('one live poetry app process is required')
    # HiLog's monotonic formatter combines mono_sec with CLOCK_REALTIME's
    # tv_nsec. That display can move backwards across a wall-clock second.
    # Epoch+nsec uses one coherent native clock; capture bracketing continues
    # to use the observer's monotonic clock independently.
    raw = shell(f"hilog -x -P {pid} -e '{EXPRESSION}' -v epoch -v nsec")
    return {'pid': int(pid), 'raw_logs': raw, 'started_monotonic': started,
            'ended_monotonic': time.monotonic(), 'log_clock': 'realtime_epoch_nsec'}


def records(state):
    if not 0 < state['started_monotonic'] <= state['ended_monotonic']:
        raise ValueError('invalid business log observation window')
    found = []
    for line in state['raw_logs'].splitlines():
        match = re.match(r'^\s*(\d+\.\d+)\s+(\d+)\s+\d+\s+[DIWEF]\s+(.+)$', line)
        if not match:
            continue
        stamp, pid, text = match.groups()
        if int(pid) != state['pid']:
            raise ValueError('business log belongs to a different app process')
        kind = None
        if 'JINGMO@SyncData:' in text and 'classic poem dataset size:' in text:
            kind = 'download'
        elif 'JINGMO@ClassicPoemDao:' in text and 'Batch insert is ' in text:
            kind = 'batch'
        elif ('JINGMO@DatasetViewModel:' in text
              and 'dataset already imported (5000 rows), skip import' in text):
            kind = 'skip'
        if kind:
            found.append((int(Decimal(stamp)*1000000000), kind, line))
    return found


def verify_observation(observation):
    before, after = observation['before'], observation['after']
    if (before['pid'] != after['pid']
            or before['ended_monotonic'] >= after['started_monotonic']):
        raise ValueError('business log snapshots are not sequential in one process')
    old = {line for _, _, line in records(before)}
    new = [(stamp, kind, line) for stamp, kind, line in records(after) if line not in old]
    if len({line for _, _, line in new}) != len(new):
        raise ValueError('duplicate business log records')
    expected = observation['expected_cycles']
    if type(expected) is not int or expected != 3:
        raise ValueError('repeat-sync workload requires three normal cycles')
    if [kind for _, kind, _ in new] not in (['download', 'batch'] * expected,
                                           ['download', 'skip'] * expected):
        raise ValueError('three downloaded-and-completed sync cycles are not proven')
    if any(new[i][0] > new[i+1][0] for i in range(len(new)-1)):
        raise ValueError('business completion logs are out of order')
    return {'completed_cycles': expected,
            'method': 'existing SyncData download and DAO completion/normal cached-data skip logs'}


def complete_sync(ui, before, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        observation = {'before': before, 'after': read_state(ui.shell), 'expected_cycles': 3}
        try:
            observation['progress'] = verify_observation(observation)
            return observation
        except ValueError as exc:
            if time.monotonic() >= deadline:
                exc.observation = observation
                raise
            time.sleep(1)


def verify_capture(observation, started, ended):
    progress = verify_observation(observation)
    if (observation['before']['ended_monotonic'] > started
            or observation['after']['started_monotonic'] < started
            or observation['after']['ended_monotonic'] > ended):
        raise ValueError('repeat-sync completion was not observed within the capture window')
    if observation.get('progress') != progress:
        raise ValueError('repeat-sync summary differs from raw business logs')
    return progress
