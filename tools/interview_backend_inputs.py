"""External backend snapshots and native-response/UI consistency checks.

Never substitutes a backend or modifies the app. Matching native response sizes,
rendered stems and independently sampled bodies is a consistency check, not a
cryptographic hash of the actual app's decrypted response.
"""
import base64
import hashlib
import gzip
import json
import re
import time
import urllib.request

URL = ('https://api-harmony-teach.itheima.net/hm/question/list?'
       'questionBankType=10&type=401&page=1&sort=0&keyword=')


def enter_question_list(ui, plan):
    """Normal entry, including expired-session recovery through the demo UI."""
    ui.shell('power-shell wakeup')
    ui.run([{'op': 'stop'}, {'op': 'launch'}])
    time.sleep(2)
    from ui_driver import UI
    if any(node.get('text') == '立即登录' for node in UI.nodes(ui.layout())):
        username = ui.find({'hint': '请输入用户名', 'match': 'exact'})
        password = ui.find({'hint': '请输入密码', 'match': 'exact'})
        if username.get('text') != 'hmheima' or not password.get('text'):
            raise ValueError('source-provided demo form is not prefilled')
        if ui.find({'type': 'Checkbox', 'match': 'exact'}).get('checked') != 'true':
            ui.tap({'type': 'Checkbox', 'match': 'exact'})
        ui.tap({'text': '立即登录', 'match': 'exact'})
    ui.run(plan['setup'])


def encoded_snapshot(path, decoded_record):
    with urllib.request.urlopen(urllib.request.Request(URL, headers={'Accept-Encoding': 'gzip'}), timeout=30) as response:
        raw = response.read()
        encoding = response.headers.get('Content-Encoding', 'identity')
        if response.status != 200 or encoding not in ('gzip', 'identity'):
            raise ValueError('unsupported or unsuccessful sampled HTTP response')
    decoded = gzip.decompress(raw) if encoding == 'gzip' else raw
    if hashlib.sha256(decoded).hexdigest() != decoded_record['sha256']:
        raise ValueError('encoded sample does not match the decoded backend snapshot')
    path.write_bytes(raw)
    path.chmod(0o600)
    return {'encoding': encoding, 'transfer_bytes': len(raw),
            'wire_sha256': hashlib.sha256(raw).hexdigest(),
            'decoded_sha256': hashlib.sha256(decoded).hexdigest()}


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


def verify_native_correspondence(raw_logs, observation, transfer_bytes):
    """Match each of five actual business successes to one native transfer.

    Continuous HiLog includes initial backfill. Match existing native/business
    clock timestamps rather than inventing a host/device clock conversion or
    treating delayed old backfill as measured requests.
    """
    from decimal import Decimal
    from interview_response_progress import records, verify_observation
    verify_observation(observation)
    old = {line for _, line in records(observation['before'])}
    successes = [(stamp, line) for stamp, line in records(observation['after']) if line not in old]
    native = native_responses(raw_logs, observation['before']['pid'])
    matched = []
    for stamp, _ in successes:
        candidates = [(epoch, line, fields) for epoch, line, fields in native
                      if abs(int(Decimal(epoch)*1000000000)-stamp) <= 1000000000]
        if len(candidates) != 1:
            raise ValueError('one unambiguous native HTTP transfer per actual business success is not proven')
        epoch, line, fields = candidates[0]
        if fields != {'size': transfer_bytes, 'errCode': 0, 'RespCode': 200}:
            raise ValueError('native transfer failed or differs from sampled encoded input')
        matched.append((epoch, line))
    if len({line for _, line in matched}) != 5:
        raise ValueError('the same native result cannot represent multiple business successes')
    return {'successful_native_http_results': 5, 'native_transfer_bytes': transfer_bytes,
            'native_result_epochs': [stamp for stamp, _ in matched],
            'actual_app_body_hash_verified': False,
            'method': 'five unique native transfer results matched one-to-one to existing successful business callbacks on the native epoch clock'}


def verify_rendered_stems(layout, record, bundle='com.itcast.pass_interview'):
    return verify_rendered_stem_frames([layout], record, bundle)


def verify_rendered_stem_frames(layouts, record, bundle='com.itcast.pass_interview'):
    """Check the complete list projection across retained normal scroll frames.

    Frames must come from outside the measured interval. This establishes only
    displayed stems, never the hash or full contents of the app's HTTP body.
    """
    from ui_driver import UI
    if not isinstance(layouts, list) or not layouts:
        raise ValueError('retained native UI frames required')
    rows = verify_snapshot(record)['data']['rows']
    texts = [node.get('text', '') for layout in layouts for node in UI.nodes(layout)
             if node.get('bundleName') == bundle and node.get('visible') != 'false']
    missing = [row['id'] for row in rows if row['stem'] not in texts]
    if missing:
        raise ValueError('complete sampled question-list projection not found in actual UI: '+','.join(missing))
    return {'question_ids': [row['id'] for row in rows], 'rendered_stems_verified': len(rows),
            'full_business_payload_verified': False}


def collect_rendered_stems(ui, record, max_swipes=8):
    """Retain ordinary list scroll frames; call only outside CPU measurement."""
    verify_snapshot(record)
    result = {'started_monotonic': time.monotonic(), 'frames': [],
              'app_injection': False, 'performance_verified': False}
    for index in range(max_swipes+1):
        result['frames'].append(ui.layout())
        try:
            result['projection'] = verify_rendered_stem_frames(result['frames'], record)
            result['ended_monotonic'] = time.monotonic()
            return result
        except ValueError as exc:
            if index == max_swipes:
                exc.observation = result
                raise
        ui.run([{'op': 'swipe', 'direction': 'up', 'count': 1,
                 'selector': {'type': 'Refresh', 'match': 'exact'}}])


def verify_capture_inputs(receipt, folder):
    """Recompute native input consistency from this CPU trial's immutable raw files."""
    from pathlib import Path
    from interview_response_progress import verify_capture
    from system_pss import start_ticks
    start, end = receipt['action_start_monotonic'], receipt['action_end_monotonic']
    responses = receipt['interview_responses']
    verify_capture(responses, start, end, receipt['pids'])
    inputs = receipt['interview_inputs']
    bracket = verify_bracket(inputs['before'], inputs['after'], start, end)
    stream = inputs['native_stream']
    pid = responses['before']['pid']
    if (not stream['logger_owner_gone'] or stream['app_pid'] != pid or
            not stream['ready_monotonic'] <= responses['before']['started_monotonic'] <= start < end <= stream['ended_monotonic'] or
            start_ticks(stream['app_stat'], pid) != start_ticks(responses['before']['raw_stat'], pid)):
        raise ValueError('native log stream does not bracket the CPU trial in the same process')
    folder = Path(folder)
    for name in ('stdout', 'stderr'):
        raw = (folder/'native-stream'/(name+'.bin')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != stream[name+'_sha256'] or len(raw) != stream[name+'_bytes']:
            raise ValueError('native stream bytes differ from the original receipt')
    encoded = inputs['encoded']
    wire = (folder/'encoded-backend.bin').read_bytes()
    decoded = gzip.decompress(wire) if encoded['encoding'] == 'gzip' else wire
    if (len(wire) != encoded['transfer_bytes'] or hashlib.sha256(wire).hexdigest() != encoded['wire_sha256'] or
            hashlib.sha256(decoded).hexdigest() != inputs['before']['sha256'] or encoded['decoded_sha256'] != inputs['before']['sha256']):
        raise ValueError('sampled wire and decoded inputs differ from the original receipt')
    native = verify_native_correspondence((folder/'native-stream/stdout.bin').read_bytes().decode('utf-8'), responses, len(wire))
    render = inputs['render']
    if not end <= render['started_monotonic'] <= render['ended_monotonic']:
        raise ValueError('render scrolling overlaps the measured workload')
    if start_ticks(inputs['render_stat'], pid) != start_ticks(stream['app_stat'], pid):
        raise ValueError('rendered list belongs to a different process')
    projection = verify_rendered_stem_frames(render['frames'], inputs['before'])
    return {'backend': bracket, 'native_http': native, 'projection': projection}
