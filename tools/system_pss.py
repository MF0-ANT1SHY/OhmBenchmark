"""Strict parsing of the kernel's process smaps_rollup Pss value."""
import re


def pss_bytes(text):
    rows=[line for line in text.splitlines() if line.strip().startswith('Pss:')]
    if len(rows)!=1:
        raise ValueError('missing or ambiguous process Pss total')
    match=re.fullmatch(r'\s*Pss:\s*(\d+)\s+kB\s*',rows[0])
    if not match:
        raise ValueError('invalid Pss value or units')
    return int(match.group(1))*1024


def read_process(remote,pid,bundle):
    if not isinstance(pid,int) or pid<=0:
        raise ValueError('invalid process identity')
    name=remote.hdc(['shell',f'cat /proc/{pid}/cmdline']).split('\x00',1)[0].strip()
    if name!=bundle:
        raise ValueError('memory belongs to a different process')
    raw=remote.hdc(['shell',f'cat /proc/{pid}/smaps_rollup'])
    value=pss_bytes(raw)
    # Reject a process exiting or a different process name after the snapshot.
    # A complete trial collector must additionally verify process start time.
    after=remote.hdc(['shell',f'cat /proc/{pid}/cmdline']).split('\x00',1)[0].strip()
    if after!=bundle:
        raise ValueError('process identity changed during memory capture')
    return {'pid':pid,'bundle':bundle,'pss_bytes':value,'raw_smaps_rollup':raw,
            'method':'kernel /proc/PID/smaps_rollup; no app instrumentation'}
