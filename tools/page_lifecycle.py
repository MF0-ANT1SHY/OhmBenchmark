"""Observe real ability windows and kernel process identity outside the app."""
import re

from system_pss import start_ticks


def observe_page(shell,bundle,node):
    if not re.fullmatch(r'[A-Za-z0-9_.]+',bundle) or node.get('bundleName')!=bundle:
        raise ValueError('page observation belongs to a different app')
    pids=shell('pidof '+bundle).split()
    if len(pids)!=1 or not pids[0].isdigit():
        raise ValueError('a unique page process is required')
    pid=int(pids[0])
    before=shell(f'cat /proc/{pid}/stat')
    cmdline=shell(f'cat /proc/{pid}/cmdline')
    after=shell(f'cat /proc/{pid}/stat')
    if cmdline.split('\x00',1)[0].strip()!=bundle or start_ticks(before,pid)!=start_ticks(after,pid):
        raise ValueError('page process identity changed during observation')
    window=str(node.get('hostWindowId',''))
    if not window.isdigit():
        raise ValueError('native window identity is missing')
    return {'pid':pid,'bundle':bundle,'window_id':window,'raw_stat_before':before,
            'raw_stat_after':after,'raw_cmdline':cmdline}


def verify_reconstructions(observations,bundle,required=10):
    if len(observations)<required+2:
        raise ValueError('initial, repeated and final page observations are required')
    identities=set();windows=[]
    for record in observations:
        pid=record['pid']
        if record['bundle']!=bundle or record['raw_cmdline'].split('\x00',1)[0].strip()!=bundle:
            raise ValueError('page belongs to a different app')
        before=start_ticks(record['raw_stat_before'],pid)
        if before!=start_ticks(record['raw_stat_after'],pid):
            raise ValueError('process changed within page observation')
        identities.add((pid,before))
        window=record['window_id']
        if not str(window).isdigit():raise ValueError('invalid native window identity')
        windows.append(str(window))
    if len(identities)!=1:
        raise ValueError('restarts cannot validate per-process font caching')
    if len(set(windows[:required+1]))!=required+1:
        raise ValueError('launches reused a window instead of reconstructing MainPage')
    if windows[-1]!=windows[required]:
        raise ValueError('final page differs from the last measured reconstruction')
    return {'reconstructions':required,'pid':next(iter(identities))[0],
            'process_start_ticks':next(iter(identities))[1],'window_ids':windows[:required+1]}
