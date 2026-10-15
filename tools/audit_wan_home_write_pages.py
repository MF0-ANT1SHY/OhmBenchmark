"""Read-only audit of original-input Wan native filesystem trials.

Reports actual whole-file traffic separately from changed preference keys.
It never calls whole-file traffic exclusive home-list bytes or accepts a case.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from audit_wan_home_primary import network_progress
from install_wan_home_cache_fixture import fixture_state,verify_deployment
from native_file_writes import EVENT,returned_file_writes,verify_retention
from system_pss import start_ticks
from wan_html_inputs import transformed
from wan_home_write_cycle import verify_backend_page

PREFERENCES='/data/app/el2/100/base/org.example.wan.ohos/haps/entry/files/persistent_storage'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state(record,folder):
    fields=record['file_identity'].split()
    if len(fields)!=7 or fields[-1]!=PREFERENCES or fields[5]!='660':
        raise ValueError('canonical native app preference identity is not proven')
    dev,ino,size,uid,gid=map(int,fields[:5])
    raw=folder/Path(record['preferences_file']).name
    if sha(raw)!=record['preferences_sha256'] or raw.stat().st_size!=size:
        raise ValueError('native preference bytes do not match stat and receipt')
    nodes={n.attrib.get('key'):n.text for n in ET.fromstring(raw.read_bytes())}
    ids={key:[row['id'] for row in json.loads(nodes[key])] for key in ('homeList','homeListCache') if key in nodes}
    if ids!=record['ids']:raise ValueError('article identities differ from retained native preference bytes')
    pid=record['pid']
    if start_ticks(record['stat'],pid)!=start_ticks(record['stat_after'],pid):
        raise ValueError('app process changed during native observation')
    log=record['native_log_receipt']
    logpath=folder/'native-logs'/Path(log['raw_file']).name
    if sha(logpath)!=log['raw_sha256'] or logpath.read_bytes().decode('utf-8',errors='replace')!=log['raw_logs']:
        raise ValueError('native request log bytes differ from receipt')
    return {'target':(dev>>20,dev&((1<<20)-1),ino),'owner':(uid,gid),
            'nodes':nodes,'ids':ids,'pid':pid,'ticks':start_ticks(record['stat'],pid),'logs':log['raw_logs']}


def cycle(row,variant,page):
    folder=Path(row['raw_artifacts'])
    if sha(folder/'result.json')!=row['receipt_sha256']:
        raise ValueError('original cycle receipt changed')
    result=json.loads((folder/'result.json').read_text())
    if result['status']!='ONE_NORMAL_PAGE_NATIVE_FILE_TRACE_CAPTURED_AUDIT_PENDING' or result['page']!=page or result['variant']!=variant:
        raise ValueError('successful original normal page is missing')
    cap=result['capture']
    if (cap['status']!='NATIVE_FILE_TRACE_CAPTURED' or cap['tracing_on_after']!='0' or cap['events_enabled_after']!='0'
            or cap['buffer_size_after']!=cap['buffer_size_before']):
        raise ValueError('native trace and configuration cleanup did not complete')
    trace=(folder/'capture/trace.txt').read_bytes()
    if hashlib.sha256(trace).hexdigest()!=cap['trace_sha256']:
        raise ValueError('native filesystem trace bytes changed')
    raw=trace.decode('utf-8')
    retention=verify_retention(raw,cap['token'],cap['cpus_before'])
    if retention!=cap['retention'] or cap['cpus_before']!=cap['cpus_after']:
        raise ValueError('native per-CPU retained window changed')
    a=state(result['before'],folder);b=state(cap['action']['after'],folder)
    if (a['pid'],a['ticks'],a['owner'])!=(b['pid'],b['ticks'],b['owner']):
        raise ValueError('normal page crosses process or file ownership identities')
    progress=network_progress(a['logs'],b['logs'],a['pid'],first_page=page)
    if progress['requested_pages']!=[page] or progress!=cap['action']['progress']:
        raise ValueError('exactly one successful normal page is not proven')
    sampled=json.loads((folder/'backend.json').read_bytes())
    if sha(folder/'backend.json')!=result['backend']['sha256'] or sampled.get('errorCode')!=0 or sampled['data']['curPage']!=page+1:
        raise ValueError('public backend sample changed or failed')
    articles=verify_backend_page(sampled,page);ids=[r['id'] for r in articles]
    if articles!=result['backend']['rows']:
        raise ValueError('public source page differs from its retained actual article input')
    if variant=='unfixed' and b['ids']['homeList']!=a['ids']['homeList']+ids:
        raise ValueError('unfixed did not persist the complete real new page')
    if variant=='fixed' and b['ids']['homeListCache']!=a['ids']['homeListCache']:
        raise ValueError('fixed first-page cache changed during load-more')
    from ui_driver import UI
    texts={n.get('text') for n in UI.nodes(cap['action']['layout_after']) if n.get('bundleName')=='org.example.wan.ohos'}
    visible=[r['id'] for r in articles if r['title'] in texts]
    if not visible or visible!=cap['action']['visible_new_ids']:
        raise ValueError('real sampled new page is not visible')
    # Cookie updates use the same PersistentStorage file. Require the final
    # native file to contain the actual successful response's cookie value;
    # otherwise its asynchronous storage work may be outside this window.
    old=set(a['logs'].splitlines());cookie_lines=[line for line in b['logs'].splitlines() if line not in old and '/network: response cookies: ' in line]
    if cookie_lines:
        expected=cookie_lines[-1].split('/network: response cookies: ',1)[1]
        actual=b['nodes'].get('cookies')
        try:
            decoded=json.loads(actual)
            if isinstance(decoded,str):actual=decoded
        except (ValueError,TypeError):pass
        if actual!=expected:
            raise ValueError('successful response cookie persistence did not complete inside the cycle')
    targets={a['target'],b['target']};left=Decimal(retention['window_begin_epoch']);right=Decimal(retention['window_end_epoch'])
    unknown=[];outside=[]
    for line in raw.splitlines():
        match=EVENT.match(line)
        if not match:continue
        target=tuple(map(int,match.group(5,6,7)));stamp=Decimal(match[3])
        if target in targets and not left<=stamp<=right:outside.append(line)
        if left<=stamp<=right and match[4].endswith('enter') and 'entry_name=persistent_storage' in line and target not in targets:
            unknown.append(line)
    if outside:raise ValueError('selected persistence file was written outside the retained workload window')
    traffic=returned_file_writes(raw,targets)
    changed=sorted(k for k in set(a['nodes'])|set(b['nodes']) if a['nodes'].get(k)!=b['nodes'].get(k))
    return {'page':page,'pid':a['pid'],'process_start_ticks':a['ticks'],'before_ids':a['ids'],'after_ids':b['ids'],
            'backend_sha256':result['backend']['sha256'],'visible_new_ids':visible,
            'file_returned_bytes':traffic['returned_bytes'],'completed_writes':traffic['completed_writes'],
            'changed_preference_keys':changed,'unbound_same_basename_entries':unknown,
            'endpoint_inode_traffic_complete':not unknown,'exclusive_home_list_bytes_verified':False,
            'native_app_writer_thread_attribution_verified':False}


def audit(path,require_complete=True):
    document=json.loads(Path(path).read_text());variants={}
    for variant,row in document['variants'].items():
        fixture,_=fixture_state(Path(row['preparation']['fixture_dir']));articles=json.loads((Path(row['preparation']['fixture_dir'])/'articles.json').read_text())
        if row['preparation']['articles']!=471 or row['preparation']['deployed_sha256']!=verify_deployment(row['preparation'],articles,fixture):
            raise ValueError('original 471-article input preparation differs from native readback')
        results=[cycle(c,variant,page) for page,c in enumerate(row['cycles'],1)]
        for a,b in zip(results,results[1:]):
            if (a['pid'],a['process_start_ticks'],a['after_ids'])!=(b['pid'],b['process_start_ticks'],b['before_ids']):
                raise ValueError('ten normal pages do not form one uninterrupted process/data sequence')
        variants[variant]={'pages':results,'file_returned_bytes':sum(r['file_returned_bytes'] for r in results),
                           'endpoint_inode_traffic_complete':all(r['endpoint_inode_traffic_complete'] for r in results)}
    complete=set(variants)=={'unfixed','fixed'} and all(len(v['pages'])==10 for v in variants.values())
    if require_complete and not complete:raise ValueError('both original ten-page trials are not complete; inspect the original live job')
    result={'status':'BOTH_TEN_PAGE_TRIALS_RECOMPUTED' if complete else 'PARTIAL_TRIAL_READ_ONLY_AUDIT',
            'complete':complete,'variants':variants,'performance_accepted':False,'exclusive_home_list_bytes_verified':False}
    if complete:
        if [p['backend_sha256'] for p in variants['unfixed']['pages']]!=[p['backend_sha256'] for p in variants['fixed']['pages']]:
            raise ValueError('paired normal public backend inputs differ')
        u,f=(variants[v]['file_returned_bytes'] for v in ('unfixed','fixed'))
        result['whole_file_unfixed_to_fixed_ratio']=u/f if f else None
        result['whole_file_threefold_criterion_met']=u>3*f
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proof',type=Path)
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    print(json.dumps(audit(args.proof,not args.allow_partial),indent=2))
