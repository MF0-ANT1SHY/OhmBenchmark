"""Accept three complete native CPU pairs for ordinary unread badge loading."""
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
from measurement_paths import capture_root
from reader_count_progress import verify_profile,verify_all_native_badges

ROOT=Path(__file__).resolve().parents[1]
CASE='sheafreader_unread_counts_n_plus_1'
COMPARISON='unfixed >= 2.0 * fixed over >= 3 rounds per variant'


def verify_recent_input(record):
    seed=record['seed_fetched_ms'];first=record['device_clock_before_ms'];last=record['device_clock_after_ms']
    if not 0<seed<=first<=last<seed+60*60000:
        raise ValueError('subscriptions were not recently fetched throughout the trial')
    database=Path(record['reader_fixture_before']['snapshot']['local_database']).resolve()
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT last_fetched,fetch_frequency FROM feeds').fetchall()
    if len(rows)!=100 or any(stamp!=seed or frequency!=60 for stamp,frequency in rows):
        raise ValueError('native frequency limits do not exclude network refresh')


def accept(cid,write=True,require_pass=True,**kwargs):
    if cid!=CASE or kwargs:
        raise ValueError('count acceptance requires three complete pairs for its own case')
    path=ROOT/'cases'/cid/'case.json';case=json.loads(path.read_text())
    if case['test_oracle']['metric']!='trace_cpu_ms' or case['test_oracle']['comparison']!=COMPARISON:
        raise ValueError('unsupported native count CPU contract')
    plan_hash=hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest()
    variants={};fixtures=set();contents=set()
    for variant in ('unfixed','fixed'):
        folder=ROOT/'artifacts/clean'/cid/variant;sign=json.loads((folder/'sign.json').read_text())
        workload=json.loads((folder/'workload.json').read_text())
        first=capture_root(folder,case,'trace_cpu_ms')/'round-1/capture.json'
        if (workload['status']!='PASS' or workload['signed_sha256']!=sign['audit']['sha256']
                or workload['plan_sha256']!=plan_hash
                or workload['native_capture_sha256']!=hashlib.sha256(first.read_bytes()).hexdigest()):
            raise ValueError('ordinary workload is not bound to its native trial')
        first_record=json.loads(first.read_text())
        verify_all_native_badges(ROOT,variant,sign['audit']['sha256'],first_record['reader_fixture_before']['content'])
        samples=[];captures=[]
        for number in (1,2,3):
            p=capture_root(folder,case,'trace_cpu_ms')/f'round-{number}'/'capture.json';r=json.loads(p.read_text())
            if (r['case']!=cid or r['variant']!=variant or r['round']!=number
                    or r['measurement_revision']!=case['measurement_revision']
                    or r['plan_sha256']!=plan_hash or r['signed_sha256']!=sign['audit']['sha256']):
                raise ValueError('native count capture provenance mismatch')
            if r['fixture_sha256']!=r['reader_fixture_before']['fixture_sha256']:
                raise ValueError('ordinary fixture identity differs')
            verify_recent_input(r)
            raw=verify_profile(r,p.with_name('trace.htrace'))
            content=r['reader_fixture_before']['content']
            if content['feeds']['rows']!=100 or content['articles']['rows']!=100000:
                raise ValueError('declared subscription/article dataset differs')
            contents.add(json.dumps(content,sort_keys=True));fixtures.add(r['fixture_sha256'])
            samples.append(raw['app_cpu_ms']);captures.append({'round':number,'trace_sha256':raw['trace_sha256'],
                'capture_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'app_cpu_ms':raw['app_cpu_ms'],
                'remote_artifacts':r['remote_artifacts']})
        variants[variant]={'samples':samples,'captures':captures,'signed_sha256':sign['audit']['sha256']}
    if len(fixtures)!=1 or len(contents)!=1:raise ValueError('all six native inputs must be identical')
    ratios=[u/f for u,f in zip(variants['unfixed']['samples'],variants['fixed']['samples'])]
    median=statistics.median(variants['unfixed']['samples'])/statistics.median(variants['fixed']['samples'])
    passed=min(ratios)>=2 and median>=2;results={}
    for variant,data in variants.items():
        results[variant]=dict(data,status='PASS' if passed else 'FAIL',metric='trace_cpu_ms',rounds=3,
            median=statistics.median(data['samples']),paired_ratios=ratios,median_ratio=median,
            plan_sha256=plan_hash,fixture_sha256=next(iter(fixtures)),legacy_evidence_reused=False,
            method='App-only native scheduling during ordinary startup and unread badge loading; 100 subscriptions, 100000 articles, complete contents preserved, recent-fetch limits exclude network work.')
        if write:(ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(results[variant],indent=2)+'\n')
    if write:
        case['test_oracle']['evidence']={'status':'measured_clean' if passed else 'measured_clean_failed',
            'metric':'trace_cpu_ms','unfixed':results['unfixed']['samples'],'fixed':results['fixed']['samples'],
            'median_ratio':median,'rounds_per_variant':3,'legacy_evidence_reused':False,'note':results['unfixed']['method']}
        path.write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    if not passed and require_pass:raise ValueError(f'paired CPU improvement below 2.0x: {ratios}')
    return results
