"""Strict native HMFS returned-byte accounting; never estimates JSON sizes.

Supports the calibrated hmfs_write_enter/exit path only. Iterated writes on a
selected inode fail closed until independently calibrated (no double counting).
Native file identity must be established by the caller. Thread-scoped callers
must also establish their native thread allowlist; file-scoped accounting never
claims that a filesystem writer belongs to the app's process.
"""
import re

EVENT = re.compile(r'^\s*.+-(\d+)\s+\(\s*(\d+|-----)\)\s+\[\d+\]\s+\S+\s+'
                   r'(\d+\.\d+):\s+hmfs_(write(?:_iter)?_(?:enter|exit)):\s+'
                   r'dev=(\d+),(\d+) ino=(\d+) offset=(\d+) size=(\d+)(?:\s+|$)(.*)$')

MARKER = re.compile(r'^\s*.+-(\d+)\s+\(\s*(\d+)\)\s+\[(\d+)\]\s+\S+\s+'
                    r'(\d+\.\d+):\s+tracing_mark_write:\s+F:([a-f0-9]{32}):(begin|end):(\d+)\s*$')


def verify_retention(raw, token, cpus):
    """Every online CPU must retain both evaluator-only boundary markers."""
    from decimal import Decimal
    if not re.fullmatch(r'[a-f0-9]{32}', token) or not cpus or len(set(cpus)) != len(cpus):
        raise ValueError('fresh native marker token and online CPU set required')
    found = {}
    for line in raw.splitlines():
        if re.search(r'\bLOST\b.*\bEVENTS\b', line):
            raise ValueError('native trace reports lost events')
        if f'F:{token}:' not in line:
            continue
        match = MARKER.fullmatch(line)
        if not match:
            raise ValueError('invalid native filesystem retention marker')
        tid, tgid, cpu, stamp, _, side, label_cpu = match.groups()
        cpu = int(cpu)
        if cpu != int(label_cpu) or cpu not in cpus or (side, cpu) in found:
            raise ValueError('retention marker CPU or uniqueness is invalid')
        found[side, cpu] = {'epoch': stamp, 'tid': int(tid), 'native_header_tgid': int(tgid)}
    if set(found) != {(side, cpu) for side in ('begin','end') for cpu in cpus}:
        raise ValueError('complete per-CPU native trace retention is not proven')
    left = max(Decimal(found['begin',cpu]['epoch']) for cpu in cpus)
    right = min(Decimal(found['end',cpu]['epoch']) for cpu in cpus)
    if not left < right:
        raise ValueError('native retention markers have no shared workload interval')
    return {'cpus': list(cpus), 'window_begin_epoch': str(left), 'window_end_epoch': str(right),
            'retained_boundary_markers': len(found)}


def returned_writes(raw, tids, targets):
    if not tids:
        raise ValueError('explicit native thread and device/inode attribution required')
    return _returned_writes(raw, set(tids), targets)


def returned_file_writes(raw, targets):
    """Count actual writes to explicitly bound files, regardless of writer.

    This is filesystem traffic, not app-thread traffic or an exclusive count
    of writes caused by one preference key. The caller must retain native
    path/device/inode bindings and report other keys changed in each commit.
    """
    result = _returned_writes(raw, None, targets)
    result['app_thread_attribution_verified'] = False
    result['scope'] = 'all native writers to caller-bound device/inodes; not exclusive home-list mutation bytes'
    return result


def _returned_writes(raw, tids, targets):
    targets = {tuple(item) for item in targets}
    if not targets:
        raise ValueError('explicit native device/inode attribution required')
    pending, completed, last = {}, [], {}
    for line in raw.splitlines():
        if re.search(r'\bLOST\b.*\bEVENTS\b', line):
            raise ValueError('native filesystem events were lost')
        if not re.search(r'\bhmfs_write(?:_iter)?_(?:enter|exit):', line):
            continue
        match = EVENT.match(line)
        if not match:
            raise ValueError('unparseable native filesystem write event')
        tid, tgid, epoch, event, major, minor, ino, offset, requested, tail = match.groups()
        tid, target = int(tid), (int(major), int(minor), int(ino))
        if target not in targets:
            continue
        if tids is not None and tid not in tids:
            raise ValueError('selected inode was written by an unattributed native thread')
        if event.startswith('write_iter_'):
            raise ValueError('selected inode uses an uncalibrated iterated write path')
        from decimal import Decimal
        stamp = Decimal(epoch)
        if stamp < last.get(tid, stamp):
            raise ValueError('native write events are out of order on one thread')
        last[tid] = stamp
        key = (tid, target)
        offset, requested = int(offset), int(requested)
        if event == 'write_enter':
            if key in pending:
                raise ValueError('overlapping native write entries on one thread/inode')
            pending[key] = {'tid': tid, 'native_header_tgid': tgid, 'device_inode': list(target),
                            'entry_epoch': epoch, 'offset': offset, 'requested_bytes': requested,
                            'entry_line': line}
        else:
            entry = pending.pop(key, None)
            result = re.fullmatch(r'res=(-?\d+)\s*', tail)
            if entry is None or result is None:
                raise ValueError('native write exit is missing its exact entry or return value')
            returned = int(result[1])
            if (returned < 0 or returned > requested or requested != entry['requested_bytes'] or
                    offset != entry['offset']+returned):
                raise ValueError('native write failed or its return/offset does not match the entry')
            completed.append(dict(entry, exit_epoch=epoch, returned_bytes=returned, exit_line=line))
    if pending:
        raise ValueError('native write entry has no completed exit')
    return {'returned_bytes': sum(row['returned_bytes'] for row in completed),
            'completed_writes': len(completed), 'writes': completed,
            'method': 'native hmfs_write_exit res, paired with matching thread/device/inode entry; not requested sizes'}
