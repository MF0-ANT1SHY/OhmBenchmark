#!/usr/bin/env python3
"""Accept paired process-PSS trials from raw kernel evidence and fresh input proof."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

from install_search_history_fixture import fixture_state
from system_pss import verify_window

ROOT=Path(__file__).resolve().parents[1]


def accept(cid,write=True,require_pass=True,*,negative_screen=False):
    # A failed mandatory first pair already disproves the all-pairs criterion.
    # This read-only screen can reject, but can never accept a partial run.
    if negative_screen and (write or require_pass):
        raise ValueError('negative screening must be read-only and cannot accept performance')
    round_count = 1 if negative_screen else 3
    path=ROOT/'cases'/cid/'case.json'
    case=json.loads(path.read_text())
    if case['test_oracle']['metric']!='app_pss_bytes':
        raise ValueError('PSS evidence cannot validate a different metric')
    plan_hash=hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest()
    variants={};identities=set()
    for variant in ('unfixed','fixed'):
        folder=ROOT/'artifacts/clean'/cid/variant
        sign=json.loads((folder/'sign.json').read_text())
        workload=json.loads((folder/'workload.json').read_text())
        if (sign['status']!='PASS' or workload['status']!='PASS'
                or workload['signed_sha256']!=sign['audit']['sha256']
                or workload['plan_sha256']!=plan_hash):
            raise ValueError('matching real UI workload is not proven')
        if cid!='interviewapp_search_history_unbounded':
            raise ValueError('fresh input preparation verification is not implemented for this memory case')
        if not workload.get('fixture',{}).get('functional_read_verified'):
            raise ValueError('normal UI read of the preference fixture is not proven')
        values=[];captures=[]
        for number in range(1,round_count+1):
            capture_path=folder/'pss-captures'/f'round-{number}'/'capture.json'
            record=json.loads(capture_path.read_text())
            if (record['status']!='CAPTURED' or record['metric']!='app_pss_bytes'
                    or record['signed_sha256']!=sign['audit']['sha256']
                    or record['plan_sha256']!=plan_hash or record['round']!=number
                    or record['case']!=cid or record['variant']!=variant):
                raise ValueError('PSS capture provenance mismatch')
            preparation=record.get('preparation') or {}
            if not record.get('input_preparation_verified') or not preparation.get('installation_verified'):
                raise ValueError('fresh per-trial input preparation is missing')
            fixture,blob=fixture_state(Path(preparation['fixture_dir']),variant)
            identity=fixture['fixture_sha256']
            if (identity!=record['fixture_sha256'] or identity!=workload['fixture']['sha256']
                    or preparation['sha256']!=identity or preparation['variant']!=variant
                    or preparation['deployed_sha256']!=hashlib.sha256(blob).hexdigest()):
                raise ValueError('prepared input differs from the validated ordinary fixture')
            values.append(verify_window(record,case['host_app']['bundle_name']))
            identities.add(identity)
            captures.append({'round':number,'capture_sha256':hashlib.sha256(capture_path.read_bytes()).hexdigest(),
                             'snapshots':len(record['snapshots'])})
        variants[variant]={'samples':values,'captures':captures,'signed_sha256':sign['audit']['sha256']}
    if len(identities)!=1:
        raise ValueError('identical semantic inputs are not proven across paired memory trials')
    ratios=[u/f for u,f in zip(variants['unfixed']['samples'],variants['fixed']['samples'])]
    median_ratio=statistics.median(variants['unfixed']['samples'])/statistics.median(variants['fixed']['samples'])
    passed=min(ratios)>=1.2 and median_ratio>=1.2
    if negative_screen and passed:
        raise ValueError('first pair is not negative; three complete pairs are required for acceptance')
    results={}
    for variant,data in variants.items():
        result={'status':'PASS' if passed else 'FAIL','metric':'app_pss_bytes','rounds':round_count,
                'samples':data['samples'],'median':statistics.median(data['samples']),
                'paired_ratios':ratios,'median_ratio':median_ratio,'plan_sha256':plan_hash,
                'signed_sha256':data['signed_sha256'],'fixture_sha256':next(iter(identities)),
                'captures':data['captures'],'legacy_evidence_reused':False,
                'method':'final absolute process PSS from raw kernel smaps_rollup; not RSS, growth or a selected peak'}
        results[variant]=result
        if write:
            (ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(result,indent=2)+'\n')
    case['test_oracle']['evidence']={'status':'measured_clean' if passed else 'measured_clean_failed',
        'metric':'app_pss_bytes','unfixed':variants['unfixed']['samples'],'fixed':variants['fixed']['samples'],
        'median_ratio':median_ratio,'rounds_per_variant':round_count,'legacy_evidence_reused':False,
        'note':'Every paired round and the median exceed 1.2x.' if passed else
               'Raw clean PSS trials are valid, but the unchanged 1.2x criterion is not met.'}
    if write:
        path.write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    if not passed and require_pass:
        raise RuntimeError(f'performance criterion not met: {ratios}')
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    args=parser.parse_args()
    results=accept(args.case)
    print(f'{args.case}: clean PSS verified, median ratio={results["unfixed"]["median_ratio"]:.3f}x')
