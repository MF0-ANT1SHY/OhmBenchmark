"""Verify three ordinary-refresh PSS-growth pairs against the frozen large-gap gate."""
import hashlib
import json
import statistics
from pathlib import Path
from weather_session_memory import gate,verify_capture,MIB
ROOT=Path(__file__).resolve().parents[1]
CASE='weatherassistant_http_session_leak'
METRIC='app_pss_growth_bytes'
REVISION='growth-v5'
COMPARISON='each of 3 pairs: unfixed lower growth >= 3 * max(fixed upper growth, 1 MiB), with >= 5 MiB unfixed growth and >= 5 MiB excess growth'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def accept(cid=CASE,write=True):
    if cid!=CASE:raise ValueError('ordinary forecast memory evidence belongs to another case')
    path=ROOT/'cases'/CASE/'case.json';case=json.loads(path.read_text())
    if (case.get('measurement_revision')!=REVISION or case['test_oracle']['metric']!=METRIC or case['test_oracle']['comparison']!=COMPARISON):
        raise ValueError('explicit prospective forecast-growth contract is required')
    revision=case.get('acceptance_revision',{})
    if revision.get('id')!=REVISION:raise ValueError('explicit archived-contract revision is required')
    for key in ('original_contract','original_workload','original_fix'):
        if digest(ROOT/revision[key])!=revision[key+'_sha256']:
            raise ValueError('historical forecast contract or repair changed: '+key)
    plan_hash=digest(path.parent/case['testcase']['workload']);variants={};fixture=None
    contract_path=ROOT/'validation/weather-sessions-growth-v5-contract.json';contract_hash=digest(contract_path)
    for variant in ('unfixed','fixed'):
        folder=ROOT/'artifacts/clean'/CASE/variant
        sign=json.loads((folder/'sign.json').read_text());workload=json.loads((folder/'workload.json').read_text())
        if (sign['status']!='PASS' or workload['status']!='PASS' or workload['signed_sha256']!=sign['audit']['sha256'] or workload['plan_sha256']!=plan_hash or digest(folder/'app-export.hap')!=sign['audit']['sha256']):
            raise ValueError('original signed weather workload is not proven')
        bounds=[];captures=[]
        for number in (1,2,3):
            trial=folder/'pss-captures'/REVISION/f'round-{number}';p=trial/'capture.json';record=json.loads(p.read_text())
            for key,expected in {'case':CASE,'variant':variant,'round':number,'metric':METRIC,'measurement_revision':REVISION,'signed_sha256':sign['audit']['sha256'],'plan_sha256':plan_hash,'contract_sha256':contract_hash}.items():
                if record.get(key)!=expected:raise ValueError('forecast memory provenance mismatch: '+key)
            if digest(trial/'plan.json')!=plan_hash or 'install bundle successfully' not in record['install_output']:
                raise ValueError('trial plan or signed installation is not proven')
            bounds.append(verify_capture(record,trial))
            if fixture is None:fixture=record['fixture_before']
            if record['fixture_before']!=fixture:raise ValueError('ordinary forecast service changed across the paired trials')
            captures.append({'round':number,'capture_sha256':digest(p),'snapshots':len(record['snapshots']),'successful_forecasts':len(record['requests'])})
        variants[variant]={'bounds':bounds,'samples':[b['median_bytes'] for b in bounds],'captures':captures,'signed_sha256':sign['audit']['sha256']}
    gates=[gate(u,f) for u,f in zip(variants['unfixed']['bounds'],variants['fixed']['bounds'])]
    if not all(row['passed'] for row in gates):raise ValueError('ordinary forecast growth does not meet the frozen large-gap gate in all three pairs')
    u_median=statistics.median(b['lower_bytes'] for b in variants['unfixed']['bounds']);f_median=statistics.median(b['upper_bytes'] for b in variants['fixed']['bounds']);median_gate=gate({'lower_bytes':u_median},{'upper_bytes':f_median})
    if not median_gate['passed']:raise ValueError('conservative median forecast-growth gate is not met')
    ratios=[r['noise_bounded_ratio'] for r in gates]
    results={v:{'status':'PASS','metric':METRIC,'rounds':3,**data,'median':statistics.median(data['samples']),'paired_ratios':ratios,'paired_gates':gates,'median_ratio':median_gate['noise_bounded_ratio'],'median_gate':median_gate,'plan_sha256':plan_hash,'contract_sha256':contract_hash,'fixture_sha256':fixture['catalogue_sha256'],'legacy_evidence_reused':False,'method':'Observed kernel PSS growth bounds around sixty successful ordinary ten-city refreshes after ten warmup returns. Gate uses unfixed lower growth and fixed upper growth with a 1 MiB denominator floor; raw signed growth remains unclamped.'} for v,data in variants.items()}
    if write:
        for v,result in results.items():(ROOT/'artifacts/clean'/CASE/v/'performance.json').write_text(json.dumps(result,indent=2)+'\n')
        case['test_oracle']['evidence']={'status':'measured_clean','metric':METRIC,**{v:data['samples'] for v,data in variants.items()},'paired_ratios':ratios,'paired_gates':gates,'median_ratio':median_gate['noise_bounded_ratio'],'rounds_per_variant':3,'legacy_evidence_reused':False,'performance_accepted':True,'note':'Conservative warmed PSS-growth gate; no whole-process 3x absolute PSS, live-malloc accounting, or file-descriptor count claim.'}
        path.write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    return results

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='write acceptance receipts only after all original pairs pass')
    args=parser.parse_args();results=accept(write=args.write)
    print(json.dumps({'case':CASE,'paired_ratios':results['unfixed']['paired_ratios'],'median_ratio':results['unfixed']['median_ratio'],'receipts_written':args.write},indent=2))
