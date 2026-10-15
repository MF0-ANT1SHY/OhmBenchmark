#!/usr/bin/env python3
"""Read-only audit of original online Wan home PSS trials, never cold-cache substitution.

This cannot accept the full case: its separate ten-page filesystem-write
mechanism must also be verified. Original trial files are never rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET

from install_wan_home_cache_fixture import fixture_state, verify_deployment
from system_pss import verify_window, start_ticks
from ui_driver import UI

ROOT=Path(__file__).resolve().parents[1]
CASE='wanharmony_persisted_home_list_growth'
BUNDLE='org.example.wan.ohos'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache(raw,key):
    root=ET.fromstring(raw);nodes=[n for n in root if n.attrib.get('key')==key]
    if root.tag!='preferences' or len(nodes)!=1 or nodes[0].tag!='string':
        raise ValueError('native home cache representation is invalid')
    rows=json.loads(nodes[0].text)
    if (not isinstance(rows,list) or not rows or any(not isinstance(row,dict) or type(row.get('id')) is not int or row['id']<=0 for row in rows)
            or len({row['id'] for row in rows})!=len(rows)):
        raise ValueError('home article identities are invalid or duplicated')
    return rows


def network_progress(before,after,pid,first_page=1):
    if type(first_page) is not int or first_page < 1:
        raise ValueError('normal load-more pages must start at a positive page')
    def records(raw):
        found=[]
        for line in raw.splitlines():
            m=re.match(r'^\s*(\d+\.\d{9})\s+(\d+)\s+\d+\s+([DIWEF])\s+\S*org\.example\.wan\.ohos/network:\s+(.*)$',line)
            if not m:continue
            if int(m[2])!=pid:raise ValueError('foreign native network-log process')
            found.append((m[1],m[3],m[4],line))
        return found
    old={row[3] for row in records(before)};new=[row for row in records(after) if row[3] not in old]
    if len({row[3] for row in new})!=len(new) or any(a[0]>b[0] for a,b in zip(new,new[1:])):
        raise ValueError('duplicated or out-of-order native network observations')
    requested=[];completed=[]
    for _,level,message,_ in new:
        if level in ('E','F'):raise ValueError('business API errors invalidate normal load-more work')
        if message.startswith('get: '):
            u=urlparse(message[5:]);m=re.fullmatch(r'/article/list/(\d+)/json',u.path)
            if m:
                page=int(m[1])
                if (u.scheme!='https' or u.hostname!='www.wanandroid.com' or u.port not in (None,443) or
                        parse_qs(u.query)!={'page':[str(page)],'page_size':['10']}):
                    raise ValueError('load-more request parameters differ from the original business path')
                requested.append(page)
        if message.startswith('(200) response: '):
            m=re.search(r'"curPage"\s*:\s*(\d+)',message[:160])
            if m:completed.append(int(m[1]))
    if not requested or requested!=list(range(first_page,first_page+len(requested))) or completed!=[x+1 for x in requested]:
        raise ValueError('complete sequential successful online load-more pages are not proven')
    return {'requested_pages':requested,'response_curpages':completed}


def visible_articles(layout,articles):
    texts={node.get('text') for node in UI.nodes(layout) if node.get('bundleName')==BUNDLE}
    selected=[(i,row['id']) for i,row in enumerate(articles) if row.get('title') in texts]
    if not selected or max(i for i,_ in selected)<len(articles)-10:
        raise ValueError('actual last loaded page is not visible')
    return selected


def paired_viewports(unfixed,fixed,articles):
    # Original workload specifies twelve swipes, not identical final pixel
    # offsets. Preserve and report differing viewports; require evidence that
    # both really reached the same last loaded page.
    u,f=visible_articles(unfixed,articles),visible_articles(fixed,articles)
    shared=sorted(set(u)&set(f))
    if not any(index>=len(articles)-10 for index,_ in shared):
        raise ValueError('paired viewports do not share an actual last-page article')
    return {'unfixed':u,'fixed':f,'shared':shared,'identical':u==f}


def trial(folder,variant,number,plan_hash,sign):
    cap=json.loads((folder/'capture.json').read_text());setup=json.loads((folder/'setup.json').read_text());after=json.loads((folder/'after.json').read_text())
    if (cap.get('status')!='DIAGNOSTIC_CAPTURED' or cap.get('supplementary_only') or
            cap.get('case')!=CASE or cap.get('variant')!=variant or cap.get('signed_sha256')!=sign['audit']['sha256']
            or cap.get('plan_sha256')!=plan_hash or (number>1 and cap.get('round')!=number)):
        raise ValueError('original trial package/plan/round binding is invalid')
    value=verify_window(cap,BUNDLE);first=cap['snapshots'][0]
    if setup['pid']!=first['pid'] or start_ticks(setup['stat'],setup['pid'])!=first['process_start_ticks']:
        raise ValueError('normal UI setup belongs to a different process')
    if not 0<after['action_start_monotonic']<after['action_end_monotonic']:
        raise ValueError('original UI actions did not complete')
    late=False
    if after['status']!='ORIGINAL_TWELVE_SWIPES_COMPLETED_INPUT_AND_NETWORK_AUDIT_PENDING':
        if variant!='unfixed' or number!=1 or 'utf-8' not in after.get('error',''):
            raise ValueError('failed ordinary UI trial cannot be used')
        recovery=json.loads((ROOT/'validation/wan-home-native-log-transport-recovery.json').read_text())
        if recovery['ui_workload_rerun'] is not False or recovery['pid']!=first['pid'] or recovery['process_start_ticks']!=first['process_start_ticks']:
            raise ValueError('original log-transport recovery changed workload/process identity')
        for name,expected in recovery['original_measurement_artifact_sha256'].items():
            if digest(folder/name)!=expected:raise ValueError('original recovered trial was altered')
        log=json.loads((folder/'recovered-hilog/receipt.json').read_text())
        if digest(folder/'recovered-hilog/late-after.stdout.bin')!=log['raw_sha256'] or log['raw_sha256']!=recovery['recovered_raw_logs_sha256']:
            raise ValueError('late recovered native log bytes changed')
        logs=log['raw_logs'];late=True
    else:
        if start_ticks(after['stat'],first['pid'])!=first['process_start_ticks']:
            raise ValueError('normal UI process changed before final observation')
        logs=after['raw_logs']
        for stage,record in (('setup',setup),('after',after)):
            log=record['native_log_receipt'];raw=folder/'native-logs'/(stage+'.stdout.bin')
            if digest(raw)!=log['raw_sha256'] or raw.read_bytes().decode('utf-8',errors='replace')!=record['raw_logs']:
                raise ValueError('byte-preserved native log provenance changed')
    prep=cap['preparation'];fixture,_=fixture_state(Path(prep['fixture_dir']));articles=json.loads((Path(prep['fixture_dir'])/'articles.json').read_text())
    if (not prep.get('installation_verified') or cap['fixture_sha256']!=fixture['fixture_sha256'] or
            prep['sha256']!=fixture['fixture_sha256'] or prep['deployed_sha256']!=verify_deployment(prep,articles,fixture)):
        raise ValueError('fresh ordinary native cache preparation is not proven')
    backend=json.loads((folder/'backend-first-page.json').read_text())
    if backend.get('errorCode')!=0:raise ValueError('normal first-page backend fetch failed')
    ids=[row['id'] for row in backend['data']['datas']]
    initial=cache(setup['raw_preferences'],'homeList' if variant=='unfixed' else 'homeListCache')
    if len(ids)!=10 or [row['id'] for row in initial]!=ids or setup['actual_first_page_ids']!=ids:
        raise ValueError('fresh normal first-page state was not reached before the window')
    progress=network_progress(setup['raw_logs'],logs,first['pid'])
    return {'pss_bytes':value,'capture_sha256':digest(folder/'capture.json'),'fixture_sha256':fixture['fixture_sha256'],
            'initial_ids':ids,'network':progress,'late_log_supplement':late,'after':after,
            'window_start':cap['action_start_monotonic'],'window_end':cap['action_end_monotonic'],'start_ticks':first['process_start_ticks']}


def audit(rounds=3):
    if type(rounds) is not int or rounds not in (1,2,3):raise ValueError('one to three saved mandatory pairs required')
    case=json.loads((ROOT/'cases'/CASE/'case.json').read_text());plan=ROOT/'cases'/CASE/case['testcase']['workload'];plan_hash=digest(plan)
    if (case['test_oracle']['metric']!='app_pss_bytes' or
            case['test_oracle']['comparison']!='unfixed >= 1.2 * fixed over >= 3 rounds per variant' or
            json.loads(plan.read_text())['measured']!=[{'op':'swipe','count':12}]):
        raise ValueError('original primary oracle or twelve-swipe workload changed')
    samples={'unfixed':[],'fixed':[]};rows=[];identities=set();previous={}
    for number in range(1,rounds+1):
        name='wan-home-first-original-workload-pair.json' if number==1 else 'wan-home-original-online-paired-pss-round-'+str(number)+'.json'
        source=json.loads((ROOT/'validation'/name).read_text());pair={}
        for variant in samples:
            row=source['variants'][variant];folder=Path(row.get('raw_artifacts') or row.get('local_raw_artifacts'))
            if not folder.is_absolute():folder=ROOT/folder
            if not folder.resolve().is_relative_to((ROOT/'artifacts/clean'/CASE/variant/'online-diagnostics').resolve()):
                raise ValueError('original trial path belongs to another case or variant')
            if digest(folder/'capture.json')!=row['capture_sha256']:raise ValueError('saved trial proof hash changed')
            sign=json.loads((ROOT/'artifacts/clean'/CASE/variant/'sign.json').read_text())
            if sign['status']!='PASS' or not sign['audit']['passed']:raise ValueError('signed business package audit failed')
            build=json.loads((ROOT/'artifacts/clean'/CASE/variant/'build.json').read_text())
            if (build['status']!='PASS' or not build['hap']['passed'] or
                    build['hap']['sha256']!=sign['unsigned_sha256'] or
                    digest(ROOT/'artifacts/clean'/CASE/variant/'app-unsigned.hap')!=sign['unsigned_sha256']):
                raise ValueError('unchanged audited business build is not proven')
            checked=trial(folder,variant,number,plan_hash,sign)
            if variant in previous and (checked['window_start']<=previous[variant]['window_end'] or checked['start_ticks']==previous[variant]['start_ticks']):
                raise ValueError('trials reused a process/window instead of fresh preparations')
            previous[variant]=checked;pair[variant]=checked;samples[variant].append(checked['pss_bytes']);identities.add(checked['fixture_sha256'])
        u,f=pair['unfixed'],pair['fixed']
        if u['initial_ids']!=f['initial_ids'] or u['network']!=f['network']:
            raise ValueError('paired normal first-page inputs or successful load-more pages differ')
        articles=cache(u['after']['raw_preferences'],'homeList')
        if len(articles)!=10*(1+len(u['network']['requested_pages'])) or [x['id'] for x in articles[:10]]!=u['initial_ids']:
            raise ValueError('unfixed persistent article array does not match completed pages')
        if [x['id'] for x in cache(f['after']['raw_preferences'],'homeListCache')]!=f['initial_ids']:
            raise ValueError('fixed first-page cache did not remain bounded')
        viewports=paired_viewports(u['after']['layout'],f['after']['layout'],articles)
        rows.append({'round':number,'unfixed_pss_bytes':u['pss_bytes'],'fixed_pss_bytes':f['pss_bytes'],
                     'raw_ratio':u['pss_bytes']/f['pss_bytes'],'successful_load_more_pages':u['network']['requested_pages'],
                     'final_article_count':len(articles),'actual_final_viewports':viewports,
                     'original_capture_sha256':{v:pair[v]['capture_sha256'] for v in pair},'unfixed_late_logs_supplemental_only':u['late_log_supplement']})
    if len(identities)!=1:raise ValueError('same semantic ordinary cache fixture not proven across trials')
    ratios=[u/f for u,f in zip(samples['unfixed'],samples['fixed'])];median=statistics.median(samples['unfixed'])/statistics.median(samples['fixed']);met=rounds==3 and min(ratios)>=1.2 and median>=1.2
    return {'case':CASE,'status':'PRIMARY_CRITERION_MET_MECHANISM_PENDING' if met else 'PRIMARY_PAIRS_AUDITED_NOT_FULL_CASE_ACCEPTANCE',
            'full_case_accepted':False,'performance_accepted':False,'metric':'app_pss_bytes','original_workload_rounds':rounds,
            'primary_criterion_fully_evaluated':rounds==3,'primary_criterion_met':met,'mandatory_pair_below_threshold':min(ratios)<1.2,
            'samples':samples,'paired_ratios':ratios,'median_ratio':median,'fixture_sha256':next(iter(identities)),
            'plan_sha256':plan_hash,'rows':rows,'pending_requirement':'Native filesystem write-volume mechanism after ten successful load-more pages; no legacy instrumented byte counters reused.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--rounds',type=int,choices=[1,2,3],default=3);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=audit(args.rounds);args.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'],result['paired_ratios'])
