"""Recheck ordinary completed search payloads and native result content."""
import hashlib
from urllib.parse import parse_qs,urlsplit
from ui_driver import UI
from ytsearch_data_service import response,CATALOGUE
BUNDLE='com.example.myapplication'

def verify_results(layout):
    nodes=[n for n in UI.nodes(layout) if n.get('bundleName')==BUNDLE and n.get('visible')!='false']
    if not any(n.get('type')=='TextInput' and n.get('text')=='electronic' and n.get('hint')=='搜索歌曲、音乐人、播客' for n in nodes):raise ValueError('complete native search input missing')
    texts={n.get('text') for n in nodes}
    for song in CATALOGUE[:2]:
        duration=f"{song['time']//60:02d}:{song['time']%60:02d}"
        if song['name'] not in texts or song['creator']+'・'+duration not in texts:raise ValueError('ordinary result title or artist/duration missing')

def verify_requests(record):
    queries=[];total=0
    for row in record['requests']:
        if not record['action_start_monotonic']<=row['start']<=row['end']<=record['action_end_monotonic']:raise ValueError('request outside measured input action')
        status,kind,body=response(row['path'])
        if status!=200 or row['status']!=status or row['error'] is not None or row['body_bytes']!=len(body) or row['sent_bytes']!=len(body) or row['body_sha256']!=hashlib.sha256(body).hexdigest():raise ValueError('ordinary response incomplete or altered')
        url=urlsplit(row['path'])
        if url.path=='/search':
            keyword=parse_qs(url.query)['keyword'][0];queries.append(keyword);total+=len(body)
    expected=['electronic'[:n] for n in range(1,11)]+['electronic']
    if record['variant']=='unfixed':
        if sorted(queries)!=sorted(expected):raise ValueError('all ten key changes and submit must reach ordinary search')
    elif record['variant']=='fixed':
        if not 1<=len(queries)<=2 or any(q!='electronic' for q in queries):raise ValueError('debounced request must preserve the final query and suppress prefixes')
    else:raise ValueError('unknown variant')
    return {'search_response_body_bytes':total,'search_queries':queries}

def verify_capture(record,folder):
    import json
    from pathlib import Path
    from scheduler_cpu import compute,window_from_markers
    folder=Path(folder)
    if record.get('status')!='CAPTURED':raise ValueError('incomplete native trial')
    if record['fixture_before']!=record['fixture_after'] or json.loads((folder/'fixture-before.json').read_text())!=record['fixture_before']:raise ValueError('ordinary service identity changed')
    for name in ('source','launcher'):
        source=Path(__file__).resolve().parent/('ytsearch_data_service.py' if name=='source' else 'ytsearch_workstation_lease.py')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=record['fixture_before'][name+'_sha256']:raise ValueError('service source differs from recorded instance')
    if not any(n.get('bundleName')==BUNDLE and n.get('type')=='TextInput' and n.get('text','')=='' for n in UI.nodes(record['initial_layout'])):raise ValueError('search did not start with empty native input')
    verify_results(record['layout']);payload=verify_requests(record)
    if payload!=record['network_payload']:raise ValueError('payload summary differs from original receipts')
    before=record['process_before']
    if before!=record['process_after'] or record['pids']!=[before['pid']] or before['start_ticks']<=0 or before['command'].split('\0',1)[0].strip()!=BUNDLE:raise ValueError('application identity differs')
    if (record['online_cpus_before']!=record['online_cpus_after'] or record['clock_before']!=record['clock_after'] or '[boot]' not in record['clock_before'] or record['buffer_size_kb_before']!=record['buffer_size_kb_after']):raise ValueError('native trace conditions differ')
    trace=folder/'trace.htrace';start,end=window_from_markers(trace,record['marker_token'],record['pids']);raw=compute(trace,record['pids'],start,end,record['online_cpus_before'])
    if raw!=record['scheduler_cpu'] or (end-start)/1e9<record['action_end_monotonic']-record['action_start_monotonic']:raise ValueError('native trace does not enclose input and results')
    return payload,raw
