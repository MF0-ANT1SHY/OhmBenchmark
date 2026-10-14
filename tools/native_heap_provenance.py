"""Independent checks for private nativeheap collector receipts.

Provenance verification is not normal-workload or performance acceptance.
"""
import hashlib
from pathlib import Path

from native_heap_events import compute
from system_pss import start_ticks


def identity(record, name):
    pid = record['pid']
    if type(pid) is not int or pid <= 0:
        raise ValueError('invalid collector process PID')
    command = record['raw_cmdline'].split('\x00', 1)[0].strip()
    if command != name:
        raise ValueError('collector process name is not exact')
    before = start_ticks(record['raw_stat_before'], pid)
    after = start_ticks(record['raw_stat_after'], pid)
    if before <= 0 or before != after:
        raise ValueError('collector process identity changed')
    return pid, before


def verify(receipt, trace, bundle, library, expected_library_sha256):
    if receipt.get('error') or receipt.get('performance_accepted') is not False:
        raise ValueError('failed or already-scored collector receipt')
    pid, _ = identity(receipt['application'], bundle)
    if receipt['pid'] != pid:
        raise ValueError('native config PID differs from the observed application')
    if not library.startswith('/data/local/tmp/') or not library.endswith('.so'):
        raise ValueError('repair library must remain evaluator-side and temporary')
    if receipt['observer_library_sha256'] != expected_library_sha256:
        raise ValueError('unmatched evaluator observer library')
    server_pid, _ = identity(receipt['profiler'], '/system/bin/hiprofilerd')
    identity(receipt['native_daemon'], '/system/bin/native_daemon')
    if library not in receipt['profiler_maps']:
        raise ValueError('repair library was not loaded in the recorded profiler')
    for key in ('app_maps_before', 'app_maps_after'):
        if library in receipt[key]:
            raise ValueError('evaluator repair library entered the application')
    if receipt['activation_receipt'] != 'hiprofilerd-only SHA256_Final snapshot; ABI=112\n':
        raise ValueError('profiler checksum repair did not acknowledge its scope')
    for name in ('hiprofilerd', 'native_daemon', 'hiprofiler_cmd'):
        if receipt['cleanup'][name]:
            raise ValueError('owned profiler cleanup is incomplete')
    if receipt.get('owned_sockets_removed') is not True:
        raise ValueError('owned control socket cleanup is not proven')
    owned = {row['pid'] for row in receipt['owned']}
    for process in (receipt['profiler'], receipt['native_daemon']):
        parent = int(process['raw_stat_before'].rsplit(')', 1)[1].split()[1])
        if parent not in owned:
            raise ValueError('profiler is not a child of a recorded owned supervisor')
    result = compute(trace, pid)
    if hashlib.sha256(Path(trace).read_bytes()).hexdigest() != receipt['trace_sha256']:
        raise ValueError('native capture differs from the collected file')
    result['collection_provenance_verified'] = True
    result['performance_accepted'] = False
    result['profiler_pid'] = server_pid
    return result
