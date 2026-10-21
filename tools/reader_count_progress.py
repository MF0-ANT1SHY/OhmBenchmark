"""Verify native unread badges and complete ordinary count-workload tables."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

BUNDLE='com.sheafreader.hm'


def database_identity(path):
    path=Path(path).resolve();digests={}
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('invalid native count-workload database')
        for table in ('feeds','articles'):
            digest=hashlib.sha256();count=0
            for row in db.execute(f'SELECT * FROM {table} ORDER BY id'):
                digest.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\n');count+=1
            digests[table]={'rows':count,'sha256':digest.hexdigest()}
        counts=dict(db.execute('SELECT feed_id,COUNT(*) FROM articles WHERE read=0 GROUP BY feed_id'))
        feeds=[row[0] for row in db.execute('SELECT id FROM feeds ORDER BY id')]
        digests['counts']={f'Journal {i}':counts.get(i,0) for i in feeds}
    return digests


def visible_badges(layout, expected, fully_visible=False):
    observed={}
    def visit(node, inherited=None):
        a=node.get('attributes',{});bundle=a.get('bundleName') or inherited
        complete = not (a.get('origBounds') and a.get('bounds') != a['origBounds'])
        if bundle==BUNDLE and a.get('type')=='Row' and a.get('visible')!='false' and (complete or not fully_visible):
            texts=[c.get('attributes',{}).get('text','') for c in node.get('children',[])
                   if c.get('attributes',{}).get('type')=='Text' and c.get('attributes',{}).get('visible')!='false']
            titles=[t for t in texts if re.fullmatch(r'Journal [1-9][0-9]*',t)]
            values=[int(t) for t in texts if t.isdigit()]
            badge_shape = not any(t not in titles and not t.isdigit() for t in texts)
            if len(titles)==1 and badge_shape:
                title=titles[0]
                if title not in expected or values not in ([expected[title]], [] if expected[title]==0 else [expected[title]]):
                    raise ValueError('rendered unread badge differs from full native database')
                if title in observed:raise ValueError('duplicate visible unread badge')
                observed[title]=expected[title]
        for child in node.get('children',[]):visit(child,bundle)
    visit(layout)
    if len(observed)<5:raise ValueError('at least five ordinary unread badges must be visible')
    return observed


def verify_profile(receipt, trace):
    from scheduler_cpu import compute, window_from_markers
    if receipt.get('status')!='CAPTURED' or receipt.get('configuration_cleanup_error'):
        raise ValueError('native count profile or cleanup failed')
    first,last=receipt['process_before'],receipt['process_after']
    if (first!=last or receipt['pids']!=[first['pid']] or first['start_ticks']<=0
            or first['command'].split('\0',1)[0].strip()!=BUNDLE):
        raise ValueError('count profile belongs to another process')
    if (receipt['online_cpus_before']!=receipt['online_cpus_after']
            or receipt['clock_before']!=receipt['clock_after'] or '[boot]' not in receipt['clock_before']
            or receipt['buffer_size_kb_before']!=receipt['buffer_size_kb_after']):
        raise ValueError('native tracing conditions changed')
    prepared=receipt['reader_fixture_before'];before=prepared['snapshot'];after=receipt['reader_fixture_after']
    for snapshot in (before,after):
        p=Path(snapshot['local_database'])
        if hashlib.sha256(p.read_bytes()).hexdigest()!=snapshot['sha256']:
            raise ValueError('native database snapshot changed')
        actual=database_identity(p)
        if actual!=snapshot['content'] or actual!=prepared['content']:
            raise ValueError('complete ordinary table contents changed')
    counts=visible_badges(receipt['reader_counts']['layout'],prepared['content']['counts'])
    if counts!=receipt['reader_counts']['badges']:
        raise ValueError('badge summary differs from native UI')
    start,end=window_from_markers(trace,receipt['marker_token'],receipt['pids'])
    action_start,action_end=receipt['action_start_monotonic'],receipt['action_end_monotonic']
    if not 0<action_start<action_end or (end-start)/1e9<action_end-action_start:
        raise ValueError('native trace does not enclose the complete startup action')
    raw=compute(trace,receipt['pids'],start,end,receipt['online_cpus_before'])
    if raw!=receipt['scheduler_cpu']:
        raise ValueError('CPU summary differs from native scheduler events')
    return raw


def verify_all_native_badges(root,variant,signed_sha256,content):
    proof=json.loads((Path(root)/'validation/reader-count-all-native-badges.json').read_text())
    if proof.get('case')!='sheafreader_unread_counts_n_plus_1' or proof.get('status')!='PASS':
        raise ValueError('complete native badge inspection is missing')
    entry=proof['variants'][variant]
    if entry['signed_sha256']!=signed_sha256:raise ValueError('badge inspection belongs to another package')
    for snapshot in (entry['before'],entry['after']):
        path=Path(snapshot['local_database'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=snapshot['sha256'] or database_identity(path)!=content:
            raise ValueError('complete badge inspection used different ordinary data')
    path=Path(entry['observations'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['observations_sha256']:
        raise ValueError('badge observations changed')
    raw=json.loads(path.read_text());seen={}
    for layout in raw['observations']:
        values=visible_badges(layout,content['counts'],fully_visible=True)
        for title,value in values.items():
            if title in seen and seen[title]!=value:raise ValueError('badge value changed while scrolling')
            seen[title]=value
    if seen!=content['counts'] or seen!=entry['badges'] or seen!=raw['seen']:
        raise ValueError('not every ordinary subscription badge was verified')
    return seen
