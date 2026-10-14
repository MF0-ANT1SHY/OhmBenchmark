"""Compute app on-CPU nanoseconds from complete native sched_switch text.

Only kernel scheduling and TGID metadata are used. No timings or counters are
read from application code. Collection/receipt provenance is a separate gate.
"""
from collections import defaultdict
from decimal import Decimal
import hashlib
from pathlib import Path
import re

SWITCH = re.compile(
    r'^\s*(?P<comm>.+)-(?P<tid>\d+)\s+(?:\(\s*(?P<tgid>\d+|-----)\s*\)\s+)?'
    r'\[(?P<cpu>\d+)\]\s+\S+\s+(?P<time>\d+\.\d+):\s+sched_switch:\s+(?P<body>.+)$')
MARKER = re.compile(
    r'^\s*.+-(?P<tid>\d+)\s+\(\s*(?P<tgid>\d+)\s*\)\s+'
    r'\[\d+\]\s+\S+\s+(?P<time>\d+\.\d+):\s+tracing_mark_write:\s+(?P<body>.+)$')


def timestamp_ns(value):
    scaled = Decimal(value) * 1000000000
    if scaled != scaled.to_integral_value():
        raise ValueError('scheduler timestamp is finer than nanosecond precision')
    return int(scaled)


def window_from_markers(path, token, app_pids):
    """Resolve evaluator-written markers using the trace's own native clock."""
    if not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('a fresh hexadecimal marker token is required')
    labels = {f'W:{token}:begin': 'begin', f'W:{token}:end': 'end'}
    found = {}
    with Path(path).open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if f'W:{token}:' not in line:
                continue
            match = MARKER.match(line)
            if not match or match['body'].strip() not in labels:
                raise ValueError('invalid native evaluator window marker')
            if int(match['tgid']) in app_pids:
                raise ValueError('measurement window marker was emitted by the application')
            label = labels[match['body'].strip()]
            if label in found:
                raise ValueError('duplicate native window marker')
            found[label] = timestamp_ns(match['time'])
    if set(found) != {'begin', 'end'} or not 0 < found['begin'] < found['end']:
        raise ValueError('complete ordered native window markers are required')
    return found['begin'], found['end']


def switches(path):
    with Path(path).open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if re.search(r'LOST\s+(?:\d+\s+)?(?:EVENTS|DATA)', line, re.I):
                raise ValueError('kernel trace reports lost scheduling data')
            stats = re.search(r'entries-in-buffer/entries-written:\s*(\d+)/(\d+)', line)
            if stats and int(stats[1]) != int(stats[2]):
                raise ValueError('kernel trace buffer is incomplete or overwritten')
            if 'sched_switch:' not in line:
                continue
            match = SWITCH.match(line)
            if not match:
                raise ValueError('unsupported or truncated sched_switch record')
            previous = re.search(r'\bprev_pid=(\d+)\b', match['body'])
            following = re.search(r'\bnext_pid=(\d+)\b', match['body'])
            if not previous or not following:
                raise ValueError('scheduler record has no complete thread transition')
            tid = int(match['tid'])
            owner = match['tgid']
            previous_tid, next_tid = int(previous[1]), int(following[1])
            next_name = re.search(r'\bnext_comm=(\S+)', match['body'])
            # Device-native records can be emitted in incoming context. The
            # prefix TGID belongs to its prefix TID, not automatically prev_pid.
            if tid == previous_tid or tid == next_tid:
                owner_tid = tid
                owner_tgid = int(owner) if owner and owner.isdigit() else None
            elif (next_tid == 0 and owner == '2'
                  and (match['comm'].strip() == f"tppmgr-idle-{int(match['cpu'])}"
                       or (match['comm'].strip() == '<...>'
                           and next_name and next_name[1] == f"tppmgr-idle-{int(match['cpu'])}"))):
                # This kernel gives each idle task a real prefix TID while the
                # scheduling payload consistently represents idle as PID 0.
                # Its task-name cache can print <...>; accept that only when
                # the payload explicitly names this CPU's idle task and TGID 2.
                owner_tid, owner_tgid = 0, 0
            else:
                raise ValueError('scheduler prefix matches neither transition thread nor known native idle task')
            yield {'cpu': int(match['cpu']), 'time_ns': timestamp_ns(match['time']),
                   'previous': previous_tid, 'next': next_tid,
                   'owner_tid': owner_tid, 'tgid': owner_tgid}


def compute(path, app_pids, start_ns, end_ns, online_cpus, thread_owners=None, include_intervals=False):
    if (type(start_ns) is not int or type(end_ns) is not int
            or not 0 < start_ns < end_ns):
        raise ValueError('a positive native-clock scheduling window is required')
    pids, cpus = set(app_pids), set(online_cpus)
    if not pids or any(type(p) is not int or p <= 0 for p in pids):
        raise ValueError('positive app TGIDs are required')
    if not cpus or any(type(c) is not int or c < 0 for c in cpus):
        raise ValueError('the native online CPU set is required')
    owners = {0: 0, **dict(thread_owners or {})}
    for event in switches(path):
        tid, owner = event['owner_tid'], event['tgid']
        if owner is not None:
            if tid in owners and owners[tid] != owner:
                raise ValueError('thread TGID changed within the scheduling trace')
            owners[tid] = owner
    active, first, last = {}, {}, {}
    per_thread = defaultdict(int)
    intervals = []
    count = 0
    for event in switches(path):
        cpu, stamp = event['cpu'], event['time_ns']
        if cpu not in cpus:
            raise ValueError('trace CPU differs from the stable native online CPU set')
        if cpu in active:
            began, tid = active[cpu]
            if stamp < began or tid != event['previous']:
                raise ValueError('missing or out-of-order CPU context switch')
            left, right = max(began, start_ns), min(stamp, end_ns)
            if right > left:
                if tid not in owners:
                    raise ValueError('scheduled thread has no native TGID attribution')
                if owners[tid] in pids:
                    per_thread[tid] += right - left
                    if include_intervals:
                        intervals.append({'tid': tid, 'cpu': cpu, 'start_ns': left, 'end_ns': right})
        else:
            first[cpu] = stamp
        active[cpu] = (stamp, event['next'])
        last[cpu] = stamp
        count += 1
    if set(first) != cpus or any(first[c] > start_ns or last[c] < end_ns for c in cpus):
        raise ValueError('scheduler events do not bracket the measured window on every online CPU')
    total = sum(per_thread.values())
    if total <= 0:
        raise ValueError('no attributable app on-CPU intervals')
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    result = {'metric': 'trace_cpu_ms', 'app_cpu_ns': total, 'app_cpu_ms': total / 1000000,
            'per_thread_ns': {str(k): v for k, v in sorted(per_thread.items())},
            'app_pids': sorted(pids), 'online_cpus': sorted(cpus),
            'window_start_ns': start_ns, 'window_end_ns': end_ns,
            'sched_switch_records': count, 'trace_sha256': digest.hexdigest(),
            'method': 'native per-CPU sched_switch intervals, clipped to the native-clock window and attributed by TGID'}
    if include_intervals:
        result['app_intervals'] = intervals
    return result
