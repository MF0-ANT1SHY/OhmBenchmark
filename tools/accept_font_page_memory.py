"""Recompute the revised font-family lifetime gate from six native PSS trials."""
import hashlib
import json
import statistics
import zipfile
from pathlib import Path
from font_page_memory import verify_capture
from measurement_paths import capture_root
ROOT=Path(__file__).resolve().parents[1]
CASE='sepweather_font_register_per_page'
REVISION='page-font-pss-v2'
COMPARISON='unfixed >= 2.0 * fixed and unfixed - fixed >= 64 MiB in each of 3 paired rounds'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def accept(write=True):
    path=ROOT/'cases'/CASE/'case.json';case=json.loads(path.read_text())
    if case.get('measurement_revision')!=REVISION or case['test_oracle']['metric']!='app_pss_bytes' or case['test_oracle']['comparison']!=COMPARISON:
        raise ValueError('explicit revised font PSS contract is required')
    reference_path=ROOT/'validation/font-page-native-reference.json';reference=json.loads(reference_path.read_text());reference_hash=digest(reference_path)
    contract=json.loads((ROOT/'validation/font-page-pss-v2-contract.json').read_text())
    if (contract['reference_sha256']!=reference_hash or contract['paired_rounds']!=3 or contract['minimum_unfixed_over_fixed']!=2.0 or contract['minimum_excess_bytes']!=64*1024*1024 or contract['warmup_visits']!=1 or contract['measured_visits']!=40):
        raise ValueError('frozen font gate or native reference changed')
    plan_hash=digest(path.parent/case['testcase']['workload']);variants={}
    for variant in ('unfixed','fixed'):
        folder=ROOT/'artifacts/clean'/CASE/variant;sign=json.loads((folder/'sign.json').read_text());workload=json.loads((folder/'workload.json').read_text())
        if sign['status']!='PASS' or workload['status']!='PASS' or workload['signed_sha256']!=sign['audit']['sha256'] or workload['plan_sha256']!=plan_hash:
            raise ValueError('native workload does not match the signed candidate')
        if sign['audit']['sha256']!=reference['preflight']['variants'][variant]['signed_sha256']:
            raise ValueError('native title reference belongs to another binary')
        hap=folder/'app-export.hap'
        if digest(hap)!=sign['audit']['sha256']:
            raise ValueError('signed font binary differs from the measured binary')
        with zipfile.ZipFile(hap) as package:
            font=package.read('resources/rawfile/DroidSansFallbackFull.ttf')
            if (hashlib.sha256(font).hexdigest()!=reference['candidate']['font_sha256'] or
                    len(font)!=reference['candidate']['font_bytes']):
                raise ValueError('bundled title font differs from the native reference')
            for name in ('DroidSansFallback-LICENSE.txt','DroidSansFallback-NOTICE.txt'):
                if not package.read('resources/rawfile/'+name).strip():
                    raise ValueError('bundled font attribution is missing')
        values=[];captures=[]
        for number in (1,2,3):
            trial=capture_root(folder,case,'app_pss_bytes')/f'round-{number}';p=trial/'capture.json';r=json.loads(p.read_text())
            for key,expected in {'case':CASE,'variant':variant,'round':number,'metric':'app_pss_bytes','measurement_revision':REVISION,'signed_sha256':sign['audit']['sha256'],'plan_sha256':plan_hash,'reference_sha256':reference_hash}.items():
                if r.get(key)!=expected:raise ValueError('font capture provenance mismatch: '+key)
            if digest(trial/'plan.json')!=plan_hash:raise ValueError('native trial plan changed')
            if 'install bundle successfully' not in r['install_output']:raise ValueError('trial installation not verified')
            values.append(verify_capture(r,trial,reference));captures.append({'round':number,'capture_sha256':digest(p),'snapshots':len(r['snapshots'])})
        variants[variant]={'samples':values,'captures':captures,'signed_sha256':sign['audit']['sha256']}
    ratios=[u/f for u,f in zip(variants['unfixed']['samples'],variants['fixed']['samples'])]
    excess=[u-f for u,f in zip(variants['unfixed']['samples'],variants['fixed']['samples'])]
    if min(ratios)<2 or min(excess)<64*1024*1024:raise ValueError('font PSS gap does not meet the frozen gate')
    median_ratio=statistics.median(variants['unfixed']['samples'])/statistics.median(variants['fixed']['samples'])
    results={v:{'status':'PASS','metric':'app_pss_bytes','rounds':3,**data,'median':statistics.median(data['samples']),'paired_ratios':ratios,'paired_excess_bytes':excess,'median_ratio':median_ratio,'plan_sha256':plan_hash,'fixture_sha256':reference_hash,'legacy_evidence_reused':False,'method':'Final absolute kernel process PSS after forty normal city-manager visits; identical native city content and title pixels.'} for v,data in variants.items()}
    if write:
        for v,r in results.items():(ROOT/'artifacts/clean'/CASE/v/'performance.json').write_text(json.dumps(r,indent=2)+'\n')
        case['test_oracle']['evidence']={'status':'measured_clean','metric':'app_pss_bytes',**{v:d['samples'] for v,d in variants.items()},'paired_ratios':ratios,'paired_excess_bytes':excess,'median_ratio':median_ratio,'rounds_per_variant':3,'legacy_evidence_reused':False,'performance_accepted':True,'note':'Revised per-page family lifetime: every pair meets 2.0x and 64 MiB; no original same-family reparse or CPU claim.'}
        path.write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    return results
