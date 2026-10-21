"""Accept reduced successful search payload transfer, not CPU or radio bytes."""
import hashlib,json,statistics
from pathlib import Path
from measurement_paths import capture_root
from ytsearch_progress import verify_capture
ROOT=Path(__file__).resolve().parents[1]
CASE='ytmusic_search_no_debounce'
METRIC='search_response_body_bytes'
COMPARISON='unfixed >= 5.0 * fixed successful search response bytes over 3 paired rounds'

def accept(cid,write=True,require_pass=True):
    if cid!=CASE:raise ValueError('search payload acceptance targets another case')
    path=ROOT/'cases'/cid/'case.json';case=json.loads(path.read_text())
    if case['test_oracle']['metric']!=METRIC or case['test_oracle']['comparison']!=COMPARISON:raise ValueError('unsupported search payload contract')
    contract=json.loads((ROOT/'validation/ytsearch-v2-formal-contract.json').read_text())
    if contract['required_ratio_each_pair_and_median']!=5 or contract['paired_rounds']!=3:raise ValueError('formal threshold changed')
    plan_hash=hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest();variants={};fixture=None
    for variant in ('unfixed','fixed'):
        folder=ROOT/'artifacts/clean'/cid/variant;sign=json.loads((folder/'sign.json').read_text());workload=json.loads((folder/'workload.json').read_text());captures=capture_root(folder,case,METRIC)
        if workload['status']!='PASS' or workload['signed_sha256']!=sign['audit']['sha256'] or workload['plan_sha256']!=plan_hash or workload['native_capture_sha256']!=hashlib.sha256((captures/'round-1/capture.json').read_bytes()).hexdigest():raise ValueError('ordinary search workload is not bound to original trial')
        samples=[];proofs=[]
        for number in (1,2,3):
            p=captures/f'round-{number}'/'capture.json';record=json.loads(p.read_text())
            if record['case']!=cid or record['variant']!=variant or record['round']!=number or record['measurement_revision']!=case['measurement_revision'] or record['signed_sha256']!=sign['audit']['sha256'] or record['plan_sha256']!=plan_hash:raise ValueError('native search provenance mismatch')
            if fixture is not None and fixture!=record['fixture_before']:raise ValueError('ordinary search input differs between trials')
            fixture=record['fixture_before'];payload,raw=verify_capture(record,p.parent);samples.append(payload[METRIC]);proofs.append({'round':number,'capture_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'trace_sha256':raw['trace_sha256'],'search_queries':payload['search_queries'],'diagnostic_app_cpu_ms':raw['app_cpu_ms']})
        variants[variant]={'samples':samples,'captures':proofs,'signed_sha256':sign['audit']['sha256']}
    ratios=[u/f for u,f in zip(variants['unfixed']['samples'],variants['fixed']['samples'])];median=statistics.median(variants['unfixed']['samples'])/statistics.median(variants['fixed']['samples']);passed=min(ratios)>=5 and median>=5;results={}
    for variant,data in variants.items():
        results[variant]=dict(data,status='PASS' if passed else 'FAIL',metric=METRIC,rounds=3,median=statistics.median(data['samples']),paired_ratios=ratios,median_ratio=median,plan_sha256=plan_hash,legacy_evidence_reused=False,method='Completed ordinary search JSON body bytes under the same ten-key input and submit; exact response contents and native results verified. No artificial delay. Excludes headers, images, and unrelated home traffic; not CPU or radio-byte improvement.')
        if write:(ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(results[variant],indent=2)+'\n')
    if write:
        case['test_oracle']['evidence']={'status':'measured_clean' if passed else 'measured_clean_failed','metric':METRIC,'unfixed':results['unfixed']['samples'],'fixed':results['fixed']['samples'],'median_ratio':median,'rounds_per_variant':3,'legacy_evidence_reused':False,'note':results['unfixed']['method']};path.write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    if require_pass and not passed:raise ValueError(f'search payload reduction below 5.0x: {ratios}')
    return results
