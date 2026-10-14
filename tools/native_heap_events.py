"""Strict malloc/free matching for official OpenHarmony 5.1 nativehook files.

Collection provenance, normal UI completion, and profiler cleanup are separate
requirements. A successful parse alone never accepts a benchmark case.
"""
import hashlib
from pathlib import Path
import struct


def varint(blob, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(blob):
            raise ValueError('truncated protobuf integer')
        byte = blob[offset]; offset += 1
        if shift == 63 and byte > 1:
            raise ValueError('protobuf integer exceeds uint64')
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('invalid protobuf integer')


def fields(blob):
    offset = 0
    result = {}
    while offset < len(blob):
        key, offset = varint(blob, offset)
        number, wire = key >> 3, key & 7
        if not number:
            raise ValueError('invalid protobuf field number')
        if wire == 0:
            value, offset = varint(blob, offset)
        elif wire in (1, 2, 5):
            if wire == 2:
                size, offset = varint(blob, offset)
            else:
                size = 8 if wire == 1 else 4
            if size > len(blob)-offset:
                raise ValueError('truncated protobuf field')
            value = blob[offset:offset+size]; offset += size
        else:
            raise ValueError('unsupported protobuf wire type')
        result.setdefault(number, []).append((wire, value))
    return result


def scalar(message, number, wire=0, default=0):
    values = message.get(number, [(wire, default)])
    if len(values) != 1 or values[0][0] != wire:
        raise ValueError('ambiguous or mistyped native protobuf field')
    return values[0][1]


def validate_config(message, pid):
    if (scalar(message, 1) != pid or scalar(message, 8) != 0
            or scalar(message, 9) != 1 or scalar(message, 17) != 1
            or scalar(message, 16) != 1 or scalar(message, 22) != 0
            or scalar(message, 24) > 1 or scalar(message, 4) > 1
            or scalar(message, 23, 2, b'') != b'monotonic'):
        raise ValueError('full accurate blocked malloc-only monotonic collection is not proven')


def records(path):
    blob = Path(path).read_bytes()
    if len(blob) < 1024:
        raise ValueError('truncated native profiler header')
    magic, length, version, segments = struct.unpack_from('<QQII', blob)
    if magic != 0x464F5250534F484F or length != len(blob) or version != 0x10000:
        raise ValueError('unsupported or incomplete native profiler container')
    if struct.unpack_from('<I', blob, 56)[0] != 0:
        raise ValueError('only standard protobuf profiler containers are implemented')
    if hashlib.sha256(blob[1024:]).digest() != blob[24:56]:
        raise ValueError('native profiler payload checksum mismatch')
    offset, count = 1024, 0
    messages = []
    while offset < len(blob):
        if len(blob)-offset < 4:
            raise ValueError('truncated native profiler record length')
        size = struct.unpack_from('<I', blob, offset)[0]; offset += 4
        if not size or size > len(blob)-offset:
            raise ValueError('truncated or empty native profiler record')
        messages.append(fields(blob[offset:offset+size])); offset += size; count += 2
    if count != segments:
        raise ValueError('native profiler record count differs from complete header')
    return blob, messages


def compute(path, pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('a positive native application PID is required')
    blob, messages = records(path)
    config_count, events = 0, []
    for message in messages:
        name = scalar(message, 1, 2, b'')
        if name == b'nativehook_config':
            if scalar(message, 2) != 0:
                raise ValueError('nativehook configuration reported an error')
            validate_config(fields(scalar(message, 3, 2, b'')), pid)
            config_count += 1
            continue
        if name != b'nativehook':
            continue
        if scalar(message, 2) != 0:
            raise ValueError('nativehook plugin reported an error')
        batch = fields(scalar(message, 3, 2, b''))
        for wire, raw in batch.get(1, []):
            if wire != 2:
                raise ValueError('invalid nativehook event batch')
            event = fields(raw)
            kinds = [number for number in range(3, 16) if number in event]
            if len(kinds) != 1:
                raise ValueError('nativehook event must have one supported payload')
            kind = kinds[0]
            if kind in (5, 6, 15):
                raise ValueError('mmap or aggregate statistics cannot replace malloc/free matching')
            if kind not in (3, 4):
                continue
            seconds, nanos = scalar(event, 1), scalar(event, 2)
            if seconds <= 0 or nanos >= 1000000000:
                raise ValueError('invalid native allocation clock')
            payload = fields(scalar(event, kind, 2))
            if scalar(payload, 1) != pid or scalar(payload, 2) <= 0:
                raise ValueError('native allocation belongs to a different or unknown process/thread')
            events.append((seconds*1000000000+nanos, kind, scalar(payload, 3), scalar(payload, 4)))
    if config_count != 1 or not events:
        raise ValueError('one matching nativehook configuration and memory events are required')
    live, unknown_frees = {}, set()
    allocations = frees = 0
    for stamp, kind, address, size in sorted(events, key=lambda item: item[0]):
        if kind == 3:
            if not address or address in live:
                raise ValueError('invalid or duplicate live native allocation address')
            live[address] = size; unknown_frees.discard(address); allocations += 1
        elif address in live:
            del live[address]; frees += 1
        elif address:
            # A free may refer to an allocation made before tracing began.
            # It cannot subtract bytes from this session's observed allocations.
            if address in unknown_frees:
                raise ValueError('repeated unmatched free suggests incomplete native allocation history')
            unknown_frees.add(address)
    return {'metric': 'nativehook_retained_bytes', 'app_pid': pid,
            'retained_bytes': sum(live.values()), 'retained_allocations': len(live),
            'observed_allocations': allocations, 'matched_frees': frees,
            'preexisting_unmatched_frees': len(unknown_frees),
            'first_event_ns': min(event[0] for event in events),
            'last_event_ns': max(event[0] for event in events),
            'trace_sha256': hashlib.sha256(blob).hexdigest(),
            'method': 'live observed malloc blocks after exact address-matched free events',
            'collection_provenance_verified': False, 'performance_accepted': False}
