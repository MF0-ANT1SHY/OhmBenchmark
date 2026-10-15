"""Compare ordinary native Wan article data using the exact business decoder.

This is evaluator-only input/rendering verification, never code in the app.
"""
import json
import hashlib
from pathlib import Path
import time
import urllib.request
import xml.etree.ElementTree as ET

from system_pss import start_ticks
from ui_driver import UI

CASE = 'wanharmony_html_decode_per_render'
BUNDLE = 'org.example.wan.ohos'
PREFERENCES = '/data/app/el2/100/base/'+BUNDLE+'/haps/entry/files/persistent_storage'
FIRST_PAGE = 'https://www.wanandroid.com/article/list/0/json?page=0&page_size=10'
REPLACEMENTS = (('&lt;', '<'), ('&gt;', '>'), ('&amp;', '&'), ('&#39;', "'"),
                ('&apos;', "'"), ('&quot;', '"'), ('&ldquo;', '“'), ('&rdquo;', '”'),
                ('&lsquo;', '‘'), ('&rsquo;', '’'), ('&mdash;', '—'))


def decode(value):
    if not isinstance(value, str):
        raise ValueError('business decoder requires a string')
    # Order matters: this is not Python html.unescape or recursive decoding.
    for source, target in REPLACEMENTS:
        value = value.replace(source, target)
    return value


def transformed(rows):
    result = []
    for row in rows:
        item = dict(row)
        item['title'] = decode(item['title'])
        item['chapterName'] = decode(item['chapterName'])
        if item.get('desc'):
            item['desc'] = decode(item['desc'])
        result.append(item)
    return result


def articles(state, *, allow_empty=False):
    root = ET.fromstring(state['raw_preferences'])
    nodes = [n for n in root if n.attrib.get('key') == 'homeList']
    if root.tag != 'preferences' or len(nodes) != 1 or nodes[0].tag != 'string':
        raise ValueError('ordinary native homeList representation is not proven')
    rows = json.loads(nodes[0].text or '')
    if (not isinstance(rows, list) or (not rows and not allow_empty) or
            any(not isinstance(r, dict) or type(r.get('id')) is not int or r['id'] <= 0 for r in rows) or
            len({r['id'] for r in rows}) != len(rows)):
        raise ValueError('ordinary article identities are missing or duplicated')
    transformed(rows)  # Validate all source-rendered string fields.
    return rows


def visible(state, rows, variant, last_page=False):
    normalized = transformed(rows) if variant == 'unfixed' else rows
    texts = {n.get('text') for n in UI.nodes(state['layout']) if n.get('bundleName') == BUNDLE}
    found = [(i, row['id']) for i, row in enumerate(normalized) if row['title'] in texts]
    if not found or (last_page and not any(i >= len(rows)-10 for i, _ in found)):
        raise ValueError('actual decoded article titles are not visible on the required page')
    return found


def verify_trial(setup, after, backend, variant):
    from audit_wan_home_primary import network_progress
    if variant not in ('unfixed', 'fixed'):
        raise ValueError('unknown business variant')
    if (after.get('status') != 'ORIGINAL_TWELVE_SWIPES_COMPLETED' or
            setup['pid'] != after['pid'] or
            start_ticks(setup['stat'], setup['pid']) != start_ticks(after['stat'], after['pid']) or
            not 0 < after['action_start_monotonic'] < after['action_end_monotonic']):
        raise ValueError('original twelve swipes are not proven in one live app process')
    if backend.get('errorCode') != 0:
        raise ValueError('normal first-page API request failed')
    expected = backend['data']['datas']
    first, final = articles(setup), articles(after)
    if len(expected) != 10 or first != (transformed(expected) if variant == 'fixed' else expected):
        raise ValueError('complete native first-page data differs from the actual external backend snapshot')
    network = network_progress(setup['raw_logs'], after['raw_logs'], setup['pid'])
    if len(final) != 10*(1+len(network['requested_pages'])) or final[:10] != first:
        raise ValueError('native articles do not match complete ordinary load-more progress')
    return {'initial_ids': [r['id'] for r in first], 'final_ids': [r['id'] for r in final],
            'network': network, 'initial_visible': visible(setup, first, variant),
            'final_visible': visible(after, final, variant, last_page=True),
            'performance_accepted': False}


def verify_pair(unfixed, fixed):
    left, right = articles(unfixed), articles(fixed)
    if transformed(left) != right:
        raise ValueError('paired native article data differ beyond the exact business HTML transform')
    u, f = visible(unfixed, left, 'unfixed', True), visible(fixed, right, 'fixed', True)
    shared = sorted(set(u)&set(f))
    if not any(i >= len(left)-10 for i, _ in shared):
        raise ValueError('paired viewports do not share an actual last-page article')
    return {'articles': len(left), 'same_complete_business_data_after_exact_transform': True,
            'unfixed_visible': u, 'fixed_visible': f, 'shared': shared,
            'performance_accepted': False}


def read_state(ui, directory, label):
    from native_hilog import snapshot
    pid = ui.shell('pidof '+BUNDLE).strip()
    if not pid.isdigit():
        raise ValueError('one live Wan app process is required')
    stat = ui.shell(f'cat /proc/{pid}/stat')
    if ui.shell(f'cat /proc/{pid}/cmdline').split('\x00', 1)[0].strip() != BUNDLE:
        raise ValueError('native article state targets another application')
    log = snapshot(int(pid), directory, label)
    result = {'pid': int(pid), 'stat': stat, 'raw_preferences': ui.shell('cat '+PREFERENCES),
              'layout': ui.layout(), 'raw_logs': log['raw_logs'], 'native_log_receipt': log}
    if start_ticks(stat, int(pid)) != start_ticks(ui.shell(f'cat /proc/{pid}/stat'), int(pid)):
        raise ValueError('native article process changed during observation')
    return result


def prepare_online(ui, directory, variant):
    directory = Path(directory)
    with urllib.request.urlopen(FIRST_PAGE, timeout=30) as response:
        raw = response.read()
        if response.status != 200:
            raise ValueError('normal backend first page failed')
    backend = json.loads(raw)
    if backend.get('errorCode') != 0 or len(backend['data']['datas']) != 10:
        raise ValueError('normal ten-article backend first page failed')
    path = directory/'backend-first-page.json'
    if path.exists():
        raise FileExistsError('preserve the original sampled backend input')
    path.write_bytes(raw)
    expected = backend['data']['datas']
    if variant == 'fixed':
        expected = transformed(expected)
    elif variant != 'unfixed':
        raise ValueError('unknown business variant')
    deadline = time.monotonic()+60
    while True:
        state = {'raw_preferences': ui.shell('cat '+PREFERENCES)}
        if articles(state, allow_empty=True) == expected:
            break
        if time.monotonic() >= deadline:
            raise ValueError('normal first-page data did not replace the native home cache')
        time.sleep(.5)
    setup = read_state(ui, directory/'native-logs', 'setup')
    if articles(setup) != expected:
        raise ValueError('normal first-page native input changed during setup')
    visible(setup, articles(setup), variant)
    identity = hashlib.sha256(json.dumps(backend['data']['datas'], ensure_ascii=False,
                                       sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    preparation = {'sha256': identity, 'variant': variant, 'backend_url': FIRST_PAGE,
                   'backend_raw_sha256': hashlib.sha256(raw).hexdigest(),
                   'normal_online_first_page_verified': True, 'native_preferences_written_by_evaluator': False,
                   'method': 'production loadList replaces its native first-page cache through the ordinary online API'}
    return {'setup': setup, 'backend': backend}, preparation


def verify_capture(observation, preparation, start, end, pids, directory):
    if (pids != [observation['setup']['pid']] or observation['after']['action_start_monotonic'] != start or
            observation['after']['action_end_monotonic'] > end or
            observation['after']['native_log_receipt']['ended_monotonic'] > end or
            observation['setup']['native_log_receipt']['ended_monotonic'] > start):
        raise ValueError('normal article work is not bracketed by the CPU window')
    directory = Path(directory)
    raw = (directory/'backend-first-page.json').read_bytes()
    backend = json.loads(raw)
    identity = hashlib.sha256(json.dumps(backend['data']['datas'], ensure_ascii=False,
                                       sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if (backend != observation['backend'] or preparation['sha256'] != identity or
            hashlib.sha256(raw).hexdigest() != preparation['backend_raw_sha256'] or
            preparation.get('normal_online_first_page_verified') is not True or
            preparation.get('native_preferences_written_by_evaluator') is not False or
            preparation['backend_url'] != FIRST_PAGE):
        raise ValueError('ordinary runtime first-page input identity is not proven')
    for label in ('setup', 'after'):
        state = observation[label]
        for stream in ('stdout', 'stderr'):
            data = (directory/'native-logs'/(label+'.'+stream+'.bin')).read_bytes()
            expected = state['native_log_receipt']['raw_sha256' if stream == 'stdout' else 'stderr_sha256']
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('original native API log bytes changed')
            if stream == 'stdout' and data.decode('utf-8', errors='replace') != state['raw_logs']:
                raise ValueError('native network callbacks differ from the original byte stream')
    progress = verify_trial(observation['setup'], observation['after'], backend, preparation['variant'])
    if observation.get('progress') != progress:
        raise ValueError('article progress summary differs from actual native input/rendering')
    return progress
