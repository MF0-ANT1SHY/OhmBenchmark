"""Verify normal question-list completions using existing business HiLog only."""
import re
import time
from decimal import Decimal
from urllib.parse import parse_qs
from system_pss import start_ticks

CASE = 'interviewapp_response_log_full_stringify'
BUNDLE = 'com.itcast.pass_interview'
URL = 'https://api-harmony-teach.itheima.net/hm/question/list?'


def read_state(shell):
    started = time.monotonic()
    pid = shell('pidof '+BUNDLE).strip()
    if not pid.isdigit():
        raise ValueError('one live Interview process is required')
    stat = shell(f'cat /proc/{pid}/stat')
    cmdline = shell(f'cat /proc/{pid}/cmdline')
    if cmdline.split('\0', 1)[0].strip() != BUNDLE:
        raise ValueError('foreign process')
    raw = shell(f"hilog -x -P {pid} -e 'question/list' -v epoch -v nsec")
    after = shell(f'cat /proc/{pid}/stat')
    if start_ticks(stat, int(pid)) != start_ticks(after, int(pid)):
        raise ValueError('process restarted during log read')
    return {'pid': int(pid), 'raw_stat': stat, 'raw_stat_after': after,
            'raw_cmdline': cmdline, 'raw_logs': raw,
            'started_monotonic': started, 'ended_monotonic': time.monotonic()}


def records(state):
    if not 0 < state['started_monotonic'] <= state['ended_monotonic']:
        raise ValueError('invalid observation window')
    pid = state['pid']
    if (state['raw_cmdline'].split('\0', 1)[0].strip() != BUNDLE or
            start_ticks(state['raw_stat'], pid) != start_ticks(state['raw_stat_after'], pid)):
        raise ValueError('invalid process identity')
    found = []
    for line in state['raw_logs'].splitlines():
        m = re.match(r'^\s*(\d+\.\d+)\s+(\d+)\s+\d+\s+([DIWEF])\s+(.+)$', line)
        if not m or URL not in m[4]:
            continue
        if int(m[2]) != pid:
            raise ValueError('foreign business log PID')
        if m[3] != 'I':
            continue
        if '/PASS_INTERVIEW_LOGGER: ' not in m[4]:
            continue
        query = m[4].split(URL, 1)[1].split(',', 1)[0]
        if parse_qs(query, keep_blank_values=True) != {
                'questionBankType': ['10'], 'type': ['401'], 'page': ['1'],
                'sort': ['0'], 'keyword': ['']}:
            continue
        # These are the two production log formats, not added measurements.
        if not (re.search(r'"code"\s*:\s*10000\b', m[4]) or
                re.search(r'\bcode=10000\s+message=', m[4])):
            continue
        found.append((int(Decimal(m[1])*1000000000), line))
    return found


def verify_observation(observation):
    before, after = observation['before'], observation['after']
    if (before['pid'] != after['pid'] or
            start_ticks(before['raw_stat'], before['pid']) != start_ticks(after['raw_stat'], after['pid']) or
            before['ended_monotonic'] >= after['started_monotonic']):
        raise ValueError('snapshots do not bracket one process')
    old = {line for _, line in records(before)}
    new = [(stamp, line) for stamp, line in records(after) if line not in old]
    if len(new) != 5 or len({line for _, line in new}) != 5:
        raise ValueError('five successful normal question-list requests are not proven')
    if any(new[i][0] > new[i+1][0] for i in range(4)):
        raise ValueError('response log clock is not ordered')
    return {'successful_question_lists': 5, 'method': 'existing successful HTTP response business logs'}


def complete(ui, before, timeout=60):
    deadline = time.monotonic()+timeout
    while True:
        observation = {'before': before, 'after': read_state(ui.shell)}
        try:
            observation['progress'] = verify_observation(observation)
            return observation
        except ValueError as exc:
            if time.monotonic() >= deadline:
                exc.observation = observation
                raise
            time.sleep(1)


def verify_capture(observation, start, end, pids):
    result = verify_observation(observation)
    if (pids != [observation['before']['pid']] or
            not 0 < start < end or observation['before']['ended_monotonic'] > start or
            observation['after']['started_monotonic'] < start or observation['after']['ended_monotonic'] > end or
            observation.get('progress') != result):
        raise ValueError('HTTP completions not verified inside CPU capture')
    return result
