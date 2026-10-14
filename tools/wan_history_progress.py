"""Verify existing Wan WebPage callbacks and ordinary native history externally.

A failed network page can emit both onPageEnd and onTitleReceive. Those callbacks
alone are never successful workload evidence. No counter is injected into the app.
"""
from decimal import Decimal
import json
import re
import time
import xml.etree.ElementTree as ET

from seed_wanharmony_history import validate_entries
from system_pss import start_ticks

BUNDLE = 'org.example.wan.ohos'
PREFERENCES = '/data/app/el2/100/base/org.example.wan.ohos/haps/entry/files/persistent_storage'
EXPRESSION = 'onTitleReceive title:|onPageEnd url:|onErrorReceive url:|onPageBegin url:'


def read_state(shell):
    started = time.monotonic()
    pid = shell('pidof '+BUNDLE).strip()
    if not pid.isdigit():
        raise ValueError('one live Wan process is required')
    pid = int(pid)
    stat = shell(f'cat /proc/{pid}/stat')
    if shell(f'cat /proc/{pid}/cmdline').split('\x00', 1)[0].strip() != BUNDLE:
        raise ValueError('native history belongs to a different process')
    raw = shell(f"hilog -x -P {pid} -e '{EXPRESSION}' -v epoch -v nsec")
    xml = shell('cat '+PREFERENCES)
    ticks = start_ticks(stat, pid)
    if start_ticks(shell(f'cat /proc/{pid}/stat'), pid) != ticks:
        raise ValueError('Wan process changed during observation')
    return {'pid': pid, 'start_ticks': ticks, 'raw_logs': raw, 'raw_xml': xml,
            'started_monotonic': started, 'ended_monotonic': time.monotonic()}


def history(state):
    root = ET.fromstring(state['raw_xml'])
    nodes = [n for n in root if n.attrib.get('key') == 'historyList']
    if root.tag != 'preferences' or len(nodes) != 1 or nodes[0].tag != 'string':
        raise ValueError('native historyList representation is not proven')
    return validate_entries(json.loads(nodes[0].text or ''))


def records(state):
    if not 0 < state['started_monotonic'] <= state['ended_monotonic']:
        raise ValueError('invalid callback observation window')
    found = []
    for line in state['raw_logs'].splitlines():
        m = re.match(r'^\s*(\d+\.\d{9})\s+(\d+)\s+\d+\s+[DIWEF]\s+\S*org\.example\.wan\.ohos/WebPage:\s+(.*)$', line)
        if not m:
            continue
        stamp, pid, message = m.groups()
        if int(pid) != state['pid']:
            raise ValueError('web callback belongs to a different process')
        for kind, prefix in [('begin', 'onPageBegin url: '), ('end', 'onPageEnd url: '),
                             ('title', 'onTitleReceive title: '), ('error', 'onErrorReceive url: ')]:
            if message.startswith(prefix):
                found.append((int(Decimal(stamp)*1000000000), kind, message[len(prefix):], line))
                break
    return found


def verify_observation(observation):
    before, after = observation['before'], observation['after']
    if ((before['pid'], before['start_ticks']) != (after['pid'], after['start_ticks'])
            or before['ended_monotonic'] >= after['started_monotonic']):
        raise ValueError('web observations are not sequential in one native process')
    expected = observation['expected_visits']
    if type(expected) is not int or expected != 5:
        raise ValueError('the ordinary history workload requires five visits')
    old = {line for _, _, _, line in records(before)}
    new = [r for r in records(after) if r[3] not in old]
    if len({r[3] for r in new}) != len(new) or any(a[0] > b[0] for a, b in zip(new, new[1:])):
        raise ValueError('duplicate or out-of-order web callbacks')
    if any(kind == 'error' for _, kind, _, _ in new):
        raise ValueError('network error pages cannot validate successful title-event work')
    first, last = history(before), history(after)
    urls = {entry['url'] for entry in first}
    if len(first) < 100 or {entry['url'] for entry in last} != urls or len(last) != len(first):
        raise ValueError('the ordinary large browsing history was not preserved')
    begins = [value for _, kind, value, _ in new if kind == 'begin']
    ends = [value for _, kind, value, _ in new if kind == 'end']
    titles = [value for _, kind, value, _ in new if kind == 'title']
    if (len(begins) != expected or ends != begins or not set(begins) <= urls
            or len(titles) != expected or any(not title.strip() for title in titles)):
        raise ValueError('five normal completed page loads and nonempty titles are not proven')
    return {'completed_visits': expected, 'history_entries_preserved': len(last),
            'method': 'existing native WebPage begin/end/title callbacks with no network-error callbacks, plus preserved production WebData history'}


class WanHistoryObserver:
    bundle = BUNDLE
    receipt_key = 'wan_history'

    def __init__(self, expected_entries):
        self.expected_entries = validate_entries(expected_entries)

    def prepare(self, ui):
        ui.find({'text': self.expected_entries[0]['title'], 'match': 'exact'})
        ui.find({'text': f'1 / {len(self.expected_entries)}', 'match': 'exact'})
        state = read_state(ui.shell)
        if history(state) != self.expected_entries:
            raise ValueError('ordinary history input was not reset before capture')
        return state

    def complete(self, ui, before):
        observation = {'before': before, 'after': read_state(ui.shell), 'expected_visits': 5}
        try:
            observation['progress'] = verify_observation(observation)
        except ValueError as exc:
            exc.observation = observation
            raise
        return observation
