#!/usr/bin/env python3
"""Accept paired clean CPU captures only after attribution/provenance checks."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def accept(cid):
    path=ROOT/'cases'/cid/'case.json'
    case=json.loads(path.read_text())
    if case['test_oracle']['metric']!='hiperf_instructions':
        raise ValueError('CPU capture cannot validate a different oracle')
    plan_hash=hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest()
    variants={}
    for variant in ['unfixed','fixed']:
        folder=ROOT/'artifacts/clean'/cid/variant
        sign=json.loads((folder/'sign.json').read_text())
        workload=json.loads((folder/'workload.json').read_text())
        if workload['status']!='PASS' or workload['plan_sha256']!=plan_hash or workload['signed_sha256']!=sign['audit']['sha256']:
            raise RuntimeError('matching real workload execution not proven')
        samples=[]
        captures=[]
        fixture_hashes=set()
        for round_no in range(1,4):
            capture_dir=folder/'cpu-captures'/f'round-{round_no}'
            receipt=json.loads((capture_dir/'capture.json').read_text())
            if receipt['status']!='CAPTURED' or receipt['plan_sha256']!=plan_hash or receipt['signed_sha256']!=sign['audit']['sha256']:
                raise RuntimeError('capture provenance mismatch')
            report_path=capture_dir/'report.json'
            report=json.loads(report_path.read_text())
            events=[e for e in report['recordSampleInfo'] if e['eventConfigName']=='hw-instructions']
            if len(events)!=1:raise RuntimeError('missing/ambiguous hardware instruction event')
            processes=[p for p in events[0]['processes'] if p['pid'] in receipt['pids']]
            if len(processes)!=len(receipt['pids']):raise RuntimeError('missing app process samples')
            for process in processes:
                if report['processNameMap'][str(process['pid'])]!=case['host_app']['bundle_name']:
                    raise RuntimeError('samples belong to a different process')
            value=sum(p['eventCount'] for p in processes)
            count=sum(t['sampleCount'] for p in processes for t in p['threads'])
            if value<=0 or count<=0 or value!=receipt['app_instruction_period_sum']:
                raise RuntimeError('invalid app instruction attribution')
            if receipt['action_end_monotonic']<=receipt['action_start_monotonic']:
                raise RuntimeError('invalid capture window')
            samples.append(value)
            fixture_hashes.add(receipt.get('fixture_sha256'))
            captures.append({'round':round_no,'report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
                             'app_samples':count,'remote_artifacts':receipt['remote_artifacts']})
        variants[variant]={'samples':samples,'captures':captures,'fixtures':fixture_hashes,
                           'signed_sha256':sign['audit']['sha256']}
    fixtures=variants['unfixed']['fixtures']|variants['fixed']['fixtures']
    if len(fixtures)!=1 or None in fixtures:raise RuntimeError('identical fixture is not proven across all rounds')
    ratios=[u/f for u,f in zip(variants['unfixed']['samples'],variants['fixed']['samples'])]
    median_ratio=statistics.median(variants['unfixed']['samples'])/statistics.median(variants['fixed']['samples'])
    if min(ratios)<1.2 or median_ratio<1.2:raise RuntimeError(f'performance criterion not met: {ratios}')
    for variant,data in variants.items():
        result={'status':'PASS','metric':'hiperf_instructions','rounds':3,'samples':data['samples'],
                'median':statistics.median(data['samples']),'paired_ratios':ratios,'median_ratio':median_ratio,
                'plan_sha256':plan_hash,'signed_sha256':data['signed_sha256'],'fixture_sha256':next(iter(fixtures)),
                'method':'app-process sampled retired-instruction period sum from system hiperf; not system total',
                'captures':data['captures'],'legacy_evidence_reused':False}
        (ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(result,indent=2)+'\n')
    case['test_oracle']['evidence']={'status':'measured_clean','metric':'hiperf_instructions',
        'unfixed':variants['unfixed']['samples'],'fixed':variants['fixed']['samples'],'median_ratio':median_ratio,
        'rounds_per_variant':3,'legacy_evidence_reused':False,'note':'Every paired round exceeds 1.2x; app process explicitly selected from the system report.'}
    case['test_oracle']['definition']='Sampled retired-instruction period sum (hw-instructions) attributed to the app process in the complete externally driven measured window.'
    path.write_text(json.dumps(case,indent=2,ensure_ascii=False)+'\n')
    print(f'{cid}: clean CPU oracle verified, median ratio={median_ratio:.3f}x')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    args=parser.parse_args()
    accept(args.case)
