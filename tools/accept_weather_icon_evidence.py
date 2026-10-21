"""Accept three pixel-complete cold launches under a declared icon delay."""
import hashlib,json,statistics,zipfile
from pathlib import Path
from measurement_paths import capture_root
from weather_icon_pixels import icon_boxes,region_hashes
from weather_icon_latency import verify_capture
from weather_service_fixture import same_instance
ROOT=Path(__file__).resolve().parents[1]
CASE='weatherassistant_remote_weather_icons'
METRIC='startup_icons_elapsed_s'
COMPARISON='unfixed conservative lower bound >= 2.0 * fixed upper bound over 3 paired rounds'


def verify_reference(root):
    root=Path(root);p=root/'validation/weather-icons-native-reference.json';ref=json.loads(p.read_text())
    if ref['case']!=CASE or ref['declared_icon_delay_s']!=4.0:raise ValueError('native image reference targets a different condition')
    path=Path(ref['reference'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=ref['reference_sha256'] or region_hashes(path,ref['boxes'])!=ref['pixels']:
        raise ValueError('native complete-image reference changed')
    with zipfile.ZipFile(root/'artifacts/clean'/CASE/'fixed/app-export.hap') as hap:
        icons={name:hashlib.sha256(hap.read('resources/rawfile/weather/'+name)).hexdigest() for name in ('sunny.img','cloudy.img','overcast.img','rain.img')}
    fixture=None
    for variant in ('unfixed','fixed'):
        row=ref['variants'][variant];sign=json.loads((root/'artifacts/clean'/CASE/variant/'sign.json').read_text())
        if sign['audit']['sha256']!=row['signed_sha256']:raise ValueError('reference belongs to another signed application')
        for name in ('observation','screenshot'):
            if hashlib.sha256(Path(row[name]).read_bytes()).hexdigest()!=row[name+'_sha256']:raise ValueError('preflight observation changed')
        if (icon_boxes(json.loads(Path(row['observation']).read_text())['layout'])!=ref['boxes']
                or region_hashes(row['screenshot'],ref['boxes'])!=ref['pixels']):raise ValueError('both native preflight pages must match')
        same_instance(row['before'],row['after'])
        if row['before']['icons_sha256']!=icons:raise ValueError('HTTP image content differs from bundled content')
        if fixture is not None:same_instance(fixture,row['before'])
        fixture=row['before']
    return ref,hashlib.sha256(p.read_bytes()).hexdigest(),fixture


def accept(cid,write=True,require_pass=True):
    if cid!=CASE:raise ValueError('icon acceptance targets another case')
    path=ROOT/'cases'/cid/'case.json';case=json.loads(path.read_text())
    if case['test_oracle']['metric']!=METRIC or case['test_oracle']['comparison']!=COMPARISON:raise ValueError('unsupported complete-icon contract')
    reference,reference_hash,fixture=verify_reference(ROOT);plan_hash=hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest();variants={}
    for variant in ('unfixed','fixed'):
        folder=ROOT/'artifacts/clean'/cid/variant;sign=json.loads((folder/'sign.json').read_text());workload=json.loads((folder/'workload.json').read_text());captures=capture_root(folder,case,METRIC)
        if (workload['status']!='PASS' or workload['signed_sha256']!=sign['audit']['sha256'] or workload['plan_sha256']!=plan_hash
                or workload['native_capture_sha256']!=hashlib.sha256((captures/'round-1/capture.json').read_bytes()).hexdigest()):raise ValueError('ordinary workload is not bound to its original trial')
        samples=[];bounds=[];proofs=[]
        for number in (1,2,3):
            p=captures/f'round-{number}'/'capture.json';record=json.loads(p.read_text())
            if (record['case']!=cid or record['variant']!=variant or record['round']!=number or record['measurement_revision']!=case['measurement_revision']
                    or record['signed_sha256']!=sign['audit']['sha256'] or record['plan_sha256']!=plan_hash or record['reference_sha256']!=reference_hash):raise ValueError('native image trial provenance mismatch')
            same_instance(fixture,record['fixture_before']);b,raw=verify_capture(record,p.parent,reference);bounds.append(b);samples.append(b['upper_s']);proofs.append({'round':number,'capture_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'trace_sha256':raw['trace_sha256'],'bounds':b,'diagnostic_app_cpu_ms':raw['app_cpu_ms']})
        variants[variant]={'samples':samples,'bounds':bounds,'captures':proofs,'signed_sha256':sign['audit']['sha256']}
    ratios=[u['lower_s']/f['upper_s'] for u,f in zip(variants['unfixed']['bounds'],variants['fixed']['bounds'])]
    median=statistics.median(b['lower_s'] for b in variants['unfixed']['bounds'])/statistics.median(variants['fixed']['samples']);passed=min(ratios)>=2 and median>=2;results={}
    for variant,data in variants.items():
        results[variant]=dict(data,status='PASS' if passed else 'FAIL',metric=METRIC,rounds=3,median=statistics.median(data['samples']),paired_ratios=ratios,median_ratio=median,plan_sha256=plan_hash,reference_sha256=reference_hash,legacy_evidence_reused=False,method='Normal cold launch until all nine native icon regions match exact complete pixels. Identical four-day forecasts and image bytes; declared 4-second remote image latency. Each unfixed lower bound must exceed twice its paired fixed upper bound. Native scheduler CPU is diagnostic, not the acceptance metric.')
        if write:(ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(results[variant],indent=2)+'\n')
    if write:
        case['test_oracle']['evidence']={'status':'measured_clean' if passed else 'measured_clean_failed','metric':METRIC,'unfixed':results['unfixed']['samples'],'fixed':results['fixed']['samples'],'median_ratio':median,'rounds_per_variant':3,'legacy_evidence_reused':False,'note':results['unfixed']['method']};path.write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    if require_pass and not passed:raise ValueError(f'conservative complete-icon improvement below 2.0x: {ratios}')
    return results
