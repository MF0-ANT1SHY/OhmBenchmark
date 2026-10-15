"""External backend snapshots and native-response/UI consistency checks.

Never substitutes a backend or modifies the app. Matching native response sizes,
rendered stems and independently sampled bodies is a consistency check, not a
cryptographic hash of the actual app's decrypted response.
"""
import base64
import hashlib
import json
import re
import time
import urllib.request

URL = ('https://api-harmony-teach.itheima.net/hm/question/list?'
       'questionBankType=10&type=401&page=1&sort=0&keyword=')


def snapshot():
    start = time.monotonic()
    with urllib.request.urlopen(URL, timeout=30) as response:
        status, body = response.status, response.read()
    record = {'url': URL, 'http_status': status,
              'started_monotonic': start, 'ended_monotonic': time.monotonic(),
              'body_base64': base64.b64encode(body).decode(),
              'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}
    verify_snapshot(record)
    return record


def verify_snapshot(record):
    body = base64.b64decode(record['body_base64'], validate=True)
    if (record['url'] != URL or record['http_status'] != 200 or
            hashlib.sha256(body).hexdigest() != record['sha256'] or
            len(body) != record['bytes'] or
            not 0 < record['started_monotonic'] <= record['ended_monotonic']):
        raise ValueError('backend snapshot identity, success or time is invalid')
    parsed = json.loads(body)
    if parsed.get('code') != 10000 or parsed.get('success') is not True:
        raise ValueError('backend business response failed')
    rows = parsed.get('data', {}).get('rows')
    if not isinstance(rows, list) or not rows:
        raise ValueError('nonempty backend question rows required')
    if (any(not isinstance(row.get('id'), str) or not row['id'] or
            not isinstance(row.get('stem'), str) or not row['stem'] for row in rows) or
            len({row['id'] for row in rows}) != len(rows)):
        raise ValueError('backend question identities or stems are invalid')
    return parsed


def verify_bracket(before, after, action_start, action_end):
    left, right = verify_snapshot(before), verify_snapshot(after)
    if (before['sha256'] != after['sha256'] or left != right or
            not before['ended_monotonic'] <= action_start < action_end <= after['started_monotonic']):
        raise ValueError('identical sampled backend bodies do not bracket this trial')
    return {'sha256': before['sha256'], 'response_bytes': before['bytes'],
            'question_ids': [row['id'] for row in left['data']['rows']],
            'method': 'independent external backend snapshots, not app-body hashing'}


def native_responses(raw_logs, pid):
    records = []
    for line in raw_logs.splitlines():
        if '[http_exec.cpp:' not in line or 'RespCode:' not in line:
            continue
        match = re.match(r'^\s*(\d+\.\d+)\s+(\d+)\s+\d+\s+[DIWEF]\s+', line)
        if not match or int(match[2]) != pid:
            raise ValueError('native HTTP result process identity is invalid')
        fields = dict(re.findall(r'(size|errCode|RespCode):(-?\d+)(?=,|\s|$)', line))
        if set(fields) != {'size', 'errCode', 'RespCode'}:
            raise ValueError('native HTTP result is incomplete')
        records.append((match[1], line, {key: int(value) for key, value in fields.items()}))
    return records


def verify_native_sizes(before_logs, after_logs, pid, transfer_bytes, expected=5):
    """Compare native curl transfer bytes, never decoded JSON body lengths.

    Compression can make these quantities different. A matching transfer size
    remains only consistency evidence, not the actual app response body hash.
    """
    old = {line for _, line, _ in native_responses(before_logs, pid)}
    new = [(stamp, line, fields) for stamp, line, fields in native_responses(after_logs, pid)
           if line not in old]
    if len(new) != expected or len({line for _, line, _ in new}) != expected:
        raise ValueError('exact normal native HTTP completion count is not proven')
    if any(fields != {'size': transfer_bytes, 'errCode': 0, 'RespCode': 200}
           for _, _, fields in new):
        raise ValueError('native response failed or differs from the expected transfer-byte size')
    return {'successful_native_http_results': expected, 'native_transfer_bytes': transfer_bytes,
            'actual_app_body_hash_verified': False}


def verify_rendered_stems(layout, record, bundle='com.itcast.pass_interview'):
    from ui_driver import UI
    rows = verify_snapshot(record)['data']['rows']
    texts = [node.get('text', '') for node in UI.nodes(layout)
             if node.get('bundleName') == bundle]
    missing = [row['id'] for row in rows if row['stem'] not in texts]
    if missing:
        raise ValueError('complete sampled question-list projection not found in actual UI: '+','.join(missing))
    return {'question_ids': [row['id'] for row in rows], 'rendered_stems_verified': len(rows),
            'full_business_payload_verified': False}
