"""Strict parsing of the kernel's process smaps_rollup Pss value."""
import re
import threading
import time


def pss_bytes(text):
    rows=[line for line in text.splitlines() if line.strip().startswith('Pss:')]
    if len(rows)!=1:
        raise ValueError('missing or ambiguous process Pss total')
    match=re.fullmatch(r'\s*Pss:\s*(\d+)\s+kB\s*',rows[0])
    if not match:
        raise ValueError('invalid Pss value or units')
    return int(match.group(1))*1024


def start_ticks(stat,pid):
    prefix,separator,rest=stat.strip().partition(' (')
    if not separator or prefix!=str(pid) or ')' not in rest:
        raise ValueError('invalid kernel process stat identity')
    fields=rest.rsplit(')',1)[1].split()
    if len(fields)<20 or not fields[19].isdigit():
        raise ValueError('missing kernel process start time')
    return int(fields[19])


def read_process(remote,pid,bundle):
    if not isinstance(pid,int) or pid<=0:
        raise ValueError('invalid process identity')
    name=remote.hdc(['shell',f'cat /proc/{pid}/cmdline']).split('\x00',1)[0].strip()
    if name!=bundle:
        raise ValueError('memory belongs to a different process')
    before_stat=remote.hdc(['shell',f'cat /proc/{pid}/stat'])
    before_start=start_ticks(before_stat,pid)
    raw=remote.hdc(['shell',f'cat /proc/{pid}/smaps_rollup'])
    value=pss_bytes(raw)
    # Names alone cannot distinguish a restarted instance of the same app.
    after=remote.hdc(['shell',f'cat /proc/{pid}/cmdline']).split('\x00',1)[0].strip()
    if after!=bundle:
        raise ValueError('process identity changed during memory capture')
    after_stat=remote.hdc(['shell',f'cat /proc/{pid}/stat'])
    if start_ticks(after_stat,pid)!=before_start:
        raise ValueError('process restarted during memory capture')
    return {'pid':pid,'bundle':bundle,'pss_bytes':value,'raw_smaps_rollup':raw,
            'process_start_ticks':before_start,'raw_stat_before':before_stat,'raw_stat_after':after_stat,
            'method':'kernel /proc/PID/smaps_rollup; no app instrumentation'}


def capture_window(remote,pid,bundle,workload,interval_s=2):
    """Observe one process throughout a normal external UI workload.

    The post-workload PSS, not growth/RSS/a selected low snapshot, is the oracle
    value. Any observer failure or process restart invalidates the whole trial.
    """
    if interval_s<=0:
        raise ValueError('sampling interval must be positive')
    baseline=read_process(remote,pid,bundle)
    samples=[]
    failures=[]
    stopped=threading.Event()

    def sample(phase):
        result=read_process(remote,pid,bundle)
        if result['process_start_ticks']!=baseline['process_start_ticks']:
            raise ValueError('process restarted within workload window')
        result.update(phase=phase,monotonic=time.monotonic())
        samples.append(result)

    def observe():
        while not stopped.wait(interval_s):
            try:
                sample('workload')
            except Exception as exc:
                failures.append(exc)
                return

    baseline.update(phase='before',monotonic=time.monotonic())
    samples.append(baseline)
    observer=threading.Thread(target=observe)
    observer.start()
    started=time.monotonic()
    try:
        workload()
    finally:
        ended=time.monotonic()
        stopped.set()
        observer.join()
    if failures:
        raise RuntimeError('PSS observer failed') from failures[0]
    sample('after')
    return {'action_start_monotonic':started,'action_end_monotonic':ended,
            'snapshots':samples,'app_pss_bytes':samples[-1]['pss_bytes']}
