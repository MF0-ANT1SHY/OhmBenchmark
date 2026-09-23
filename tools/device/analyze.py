#!/usr/bin/env python3
"""Extract oracle metrics from hitrace .chtrace (ftrace text) + companion hilog.

Metric primitives:
  - pid_first_ts(trace, pid): first scheduler appearance of pid (process start)
  - cpu_time(trace, pid, t0, t1): on-CPU milliseconds of pid within window
  - hilog_marker_dt(hlog, pid, marker): wall ms from first pid line to marker line
  - startup_cpu_ms(trace, hlog, pid, marker): cpu time between process start and
    marker, using the first-pid-line anchor to map wall clock -> trace clock.
"""
import re
import sys
from datetime import datetime

LINE = re.compile(
    r'^\s*(?P<task>\S+)-(?P<pid>\d+)\s+\(\s*(?P<tgid>\d+)\)\s+\[(?P<cpu>\d+)\]\s*'
    r'(?P<flags>[.\dHZx]*)\s*(?P<ts>\d+\.\d+):\s*(?P<rest>.*)$')
SWITCH = re.compile(r'sched_switch:.*?prev_pid=(?P<prev>\d+).*?next_pid=(?P<next>\d+)')
WAKEUP = re.compile(r'sched_wakeup(?:_rt)?:.*?pid=(?P<pid>\d+)')


def _clean(hlog_path):
    """hilog tee files may embed NUL markers; strip them per line."""
    with open(hlog_path, 'r', errors='replace') as f:
        for line in f:
            yield line.replace('\x00', '')


def events(path, wanted_pids=None, wanted_fns=None):
    pids = set(wanted_pids or [])
    fns = tuple(wanted_fns or [])
    with open(path, 'r', errors='replace') as f:
        for line in f:
            if wanted_fns and not line.rstrip().endswith(fns) and not any(fn in line for fn in fns):
                if not pids:
                    continue
            m = LINE.match(line)
            if not m:
                continue
            pid = int(m.group('pid'))
            if pids and pid not in pids and f'pid={pid} ' not in line and f'prev_pid={pid} ' not in line:
                continue
            yield m


def pid_first_ts(path, pid):
    for m in events(path, wanted_pids=[pid], wanted_fns=['sched_wakeup', 'sched_switch']):
        rest = m.group('rest')
        if (f'pid={pid} ' in rest or f'prev_pid={pid} ' in rest or f'next_pid={pid} ' in rest
                or int(m.group('pid')) == pid):
            return float(m.group('ts'))
    return None


def cpu_time(path, pid, t0=None, t1=None):
    """On-CPU ms of pid between trace timestamps t0..t1 (whole range if None)."""
    entered = {}
    total = 0.0
    last_ts = None
    for m in events(path, wanted_fns=['sched_switch']):
        ts = float(m.group('ts'))
        if (t0 and ts < t0) or (t1 and ts > t1):
            last_ts = ts
            continue
        sm = SWITCH.search(m.group('rest'))
        if not sm:
            continue
        cpu = m.group('cpu')
        prev, nxt = int(sm.group('prev')), int(sm.group('next'))
        if nxt == pid:
            entered[cpu] = ts
        elif prev == pid and cpu in entered:
            total += ts - entered.pop(cpu)
        last_ts = ts
    # still running at window end
    if last_ts is not None:
        for v in entered.values():
            total += (t1 or last_ts) - v
    return total * 1000.0


def hilog_lines(hlog_path, pid=None, contains=None):
    out = []
    for line in _clean(hlog_path):
        if re.match(r'^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}', line):
            if pid and f' {pid} ' not in line[:40]:
                continue
            if contains and contains not in line:
                continue
            out.append(line.rstrip())
    return out


def _wall_ms(line):
    dt = datetime.strptime(datetime.now().strftime('%Y-') + line[:18], '%Y-%m-%d %H:%M:%S.%f')
    return dt.timestamp() * 1000.0


def hilog_marker_dt(hlog_path, pid, marker):
    """Wall-clock ms between the pid's first hilog line and the marker line."""
    first = None
    hit = None
    for line in _clean(hlog_path):
        if not re.match(r'^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}', line):
            continue
        head = line[:36]
        if f' {pid} ' not in head and not head.rstrip().endswith(str(pid)):
            # hilog format: MM-DD HH:MM:SS.mmm PID TID ...
            if f' {pid} ' not in line[:44]:
                continue
        if first is None:
            first = line
        if marker in line:
            hit = line
            break
    if first is None or hit is None:
        return None
    return _wall_ms(hit) - _wall_ms(first)


def startup_cpu_ms(trace, hlog, pid, marker):
    t_first = pid_first_ts(trace, pid)
    if t_first is None:
        return None, None
    dt = hilog_marker_dt(hlog, pid, marker)
    if dt is None:
        return None, None
    t_end = t_first + dt / 1000.0
    return cpu_time(trace, pid, t0=t_first, t1=t_end), dt


if __name__ == '__main__':
    trace, hlog, pid, marker = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    cpu, dt = startup_cpu_ms(trace, hlog, pid, marker)
    print(f'startup_cpu_ms={cpu} startup_wall_ms={dt}')
