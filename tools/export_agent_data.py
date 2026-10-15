#!/usr/bin/env python3
"""Export the business-only unfixed app and app-scoped native diagnostic data.

The benchmark checkout is evaluator-private. Never expose it as an agent's
workspace: it contains fixed sources, repair diffs and performance oracles.
"""
import argparse
import ast
import copy
import hashlib
import json
import subprocess
from pathlib import Path

from clean_sources import app_ref
from remote_device import Remote
from scheduler_cpu import compute, window_from_markers
from system_pss import verify_window
from hap_profile_validity import verify_installable_profile
from accept_cpu_evidence import accept as validate_cpu
from accept_trace_evidence import accept as validate_trace
from accept_pss_evidence import accept as validate_pss

ROOT = Path(__file__).resolve().parents[1]


def require_accepted_case(cid, case, round_number):
    evidence = case.get('test_oracle', {}).get('evidence', {})
    if (evidence.get('status') != 'measured_clean' or
            case.get('disposition', {}).get('status') == 'skipped_by_user'):
        raise ValueError('agent export requires accepted full evidence; pending and negative cases are excluded')
    if type(round_number) is not int or not 1 <= round_number <= 3:
        raise ValueError('selected round must belong to the three accepted paired rounds')
    metric = case['test_oracle']['metric']
    validator = {'hiperf_instructions':validate_cpu, 'trace_cpu_ms':validate_trace,
                 'app_pss_bytes':validate_pss}.get(metric)
    if validator is None:
        raise ValueError('agent data export is not implemented for this metric')
    # Recompute the original full criterion read-only. Flags or one favorable
    # captured round cannot authorize an export, including after early rejection.
    results = validator(cid, write=False)
    if set(results) != {'unfixed','fixed'}:
        raise ValueError('both complete paired variants are required')
    for variant, result in results.items():
        if (result['status'] != 'PASS' or result['rounds'] != 3 or result['metric'] != metric or
                len(result['samples']) != 3 or evidence.get(variant) != result['samples']):
            raise ValueError('full accepted evidence differs from recomputed paired measurements')


def reproduction_script():
    """Package the normal UI actions without evaluator/profiler dependencies."""
    parsed=ast.parse((ROOT/'tools/ui_driver.py').read_text())
    ui=next(node for node in parsed.body if isinstance(node,ast.ClassDef) and node.name=='UI')
    ui.body=[node for node in ui.body if not isinstance(node,ast.FunctionDef) or node.name!='profiled']
    prefix='import argparse,json,re,shlex,subprocess,time,uuid\nfrom pathlib import Path\n\n'
    main='''
if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Run ordinary application UI actions through hdc.')
    parser.add_argument('--phase',choices=['all','setup','measured','verify'],default='all')
    args=parser.parse_args()
    plan=json.loads(Path(__file__).with_name('workload.json').read_text())
    def shell(command):
        result=subprocess.run(['hdc','shell',command],capture_output=True,text=True,check=True,timeout=90)
        return result.stdout
    ui=UI(shell,plan['bundle'],plan['ability'])
    if args.phase in ('all','setup'):
        ui.run([{'op':'stop'},{'op':'launch'}]);ui.run(plan['setup'])
    if args.phase in ('all','measured'):ui.run(plan['measured'])
    if args.phase in ('all','verify'):ui.run(plan['verify'])
'''
    return prefix+ast.unparse(ui)+'\n'+main


def app_report(report, pids, bundle):
    selected = set(pids)
    if not selected:
        raise ValueError('empty app process selection')
    if any(report['processNameMap'].get(str(pid)) != bundle for pid in selected):
        raise ValueError('process identity mismatch')
    events = []
    for event in report['recordSampleInfo']:
        processes = [copy.deepcopy(p) for p in event['processes'] if p['pid'] in selected]
        if {p['pid'] for p in processes} != selected:
            raise ValueError('selected app missing from event')
        events.append({'eventConfigName': event['eventConfigName'],
                       'eventCount': sum(p['eventCount'] for p in processes), 'processes': processes})
    symbols, files, tids = set(), set(), set()
    def references(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'symbol' and child != -1:
                    symbols.add(str(child))
                elif key == 'fileId':
                    files.add(child)
                elif key == 'tid':
                    tids.add(str(child))
                references(child)
        elif isinstance(value, list):
            for child in value:
                references(child)
    references(events)
    # Some device reports reference anonymous ArkTS/JIT frames without an entry
    # in SymbolMap. Keep their sample counts and IDs; do not invent a function
    # name or silently remove these business frames.
    symbol_files = {}
    for event in events:
        for process in event['processes']:
            for thread in process['threads']:
                for lib in thread['libs']:
                    for function in lib['functions']:
                        sid = str(function['symbol'])
                        if sid in symbol_files and symbol_files[sid] != lib['fileId']:
                            raise ValueError('ambiguous symbol library')
                        symbol_files[sid] = lib['fileId']
    raw_files = list(report['symbolsFileList'])
    unknown_file = len(raw_files)
    raw_files.append('[unresolved]')
    symbol_map = {}
    for sid in sorted(symbols, key=int):
        symbol_map[sid] = copy.deepcopy(report['SymbolMap'].get(sid,
            {'file': symbol_files.get(sid, unknown_file), 'symbol': '[unresolved]'}))
    files.update(s['file'] for s in symbol_map.values())
    file_ids = {old: new for new, old in enumerate(sorted(files))}
    for symbol in symbol_map.values():
        symbol['file'] = file_ids[symbol['file']]
    def remap(value):
        if isinstance(value, dict):
            if 'fileId' in value:
                value['fileId'] = file_ids[value['fileId']]
            for child in value.values():
                remap(child)
        elif isinstance(value, list):
            for child in value:
                remap(child)
    remap(events)
    result = {k: report[k] for k in ('deviceTime', 'deviceType', 'osVersion') if k in report}
    result.update({'totalRecordSamples': sum(t['sampleCount'] for e in events for p in e['processes'] for t in p['threads']),
                   'processNameMap': {str(pid): bundle for pid in sorted(selected)},
                   'threadNameMap': {tid: report['threadNameMap'][tid] for tid in sorted(tids, key=int)},
                   'symbolsFileList': [raw_files[old] for old in sorted(files)],
                   'SymbolMap': symbol_map, 'recordSampleInfo': events})
    return result


def app_scheduler_report(trace, capture, bundle):
    before, after = capture['process_before'], capture['process_after']
    if (before != after or capture['pids'] != [before['pid']]
            or bundle not in before['command']
            or capture['online_cpus_before'] != capture['online_cpus_after']
            or capture['clock_before'] != capture['clock_after']
            or '[boot]' not in capture['clock_before']):
        raise ValueError('native scheduler process or environment identity mismatch')
    start, end = window_from_markers(trace, capture['marker_token'], capture['pids'])
    native = compute(trace, capture['pids'], start, end, capture['online_cpus_before'], include_intervals=True)
    intervals = native.pop('app_intervals')
    if native != capture['scheduler_cpu']:
        raise ValueError('scheduler profile differs from the captured native evidence')
    # Whitelist app-only scheduling data, never copy the raw system trace,
    # evaluator markers, fixture identities, ratios or private artifact paths.
    return {'schema': 'app_scheduler_profile_v1', 'processNameMap': {str(before['pid']): bundle},
            'duration_ns': end-start, 'app_cpu_ns': native['app_cpu_ns'],
            'per_thread_ns': native['per_thread_ns'],
            'intervals': [{'tid': x['tid'], 'cpu': x['cpu'], 'start_ns': x['start_ns']-start,
                           'duration_ns': x['end_ns']-x['start_ns']} for x in intervals],
            'method': 'App-only native scheduling intervals; timestamps are relative to the recorded window.'}


def app_memory_report(capture, bundle):
    verify_window(capture, bundle)
    first = capture['snapshots'][0]
    origin = first['monotonic']
    # Kernel identity and raw totals are verified above. Export the observed
    # values, not evaluator fixture, preparation, comparison or oracle fields.
    return {'schema': 'app_memory_profile_v1', 'processNameMap': {str(first['pid']): bundle},
            'metric': 'process_pss_bytes',
            'workload_start_ns': round((capture['action_start_monotonic']-origin)*1000000000),
            'workload_end_ns': round((capture['action_end_monotonic']-origin)*1000000000),
            'snapshots': [{'phase': s['phase'], 'time_ns': round((s['monotonic']-origin)*1000000000),
                           'pss_bytes': s['pss_bytes']} for s in capture['snapshots']],
            'method': 'App-only kernel process PSS snapshots; times are relative to the first observation.'}


def export(cid, destination, symptom, round_number, remote_name='cityuPC', include_source=False):
    case = json.loads((ROOT/'cases'/cid/'case.json').read_text())
    require_accepted_case(cid, case, round_number)
    folder = ROOT/'artifacts/clean'/cid/'unfixed'
    build = json.loads((folder/'build.json').read_text())
    sign = json.loads((folder/'sign.json').read_text())
    metric=case.get('test_oracle',{}).get('metric','hiperf_instructions')
    if metric not in ('hiperf_instructions','trace_cpu_ms','app_pss_bytes'):
        raise ValueError('agent data export is not implemented for this metric')
    capture_folder = folder/{'trace_cpu_ms':'trace-captures','app_pss_bytes':'pss-captures','hiperf_instructions':'cpu-captures'}[metric]/f'round-{round_number}'
    capture = json.loads((capture_folder/'capture.json').read_text())
    hap = folder/'app-export.hap'
    plan = ROOT/'cases'/cid/case['testcase']['workload']
    if (build.get('status')!='PASS' or not build.get('hap',{}).get('passed')
            or sign.get('unsigned_sha256')!=build['hap']['sha256']):
        raise ValueError('signature belongs to a different clean build')
    unsigned=folder/'app-unsigned.hap'
    if hashlib.sha256(unsigned.read_bytes()).hexdigest()!=build['hap']['sha256']:
        raise ValueError('unsigned artifact differs from audited clean build')
    if sign['status'] != 'PASS' or not sign['audit']['passed'] or capture['status'] != 'CAPTURED' or capture['signed_sha256'] != sign['audit']['sha256']:
        raise ValueError('unmatched capture/package')
    if not hap.exists() or hashlib.sha256(hap.read_bytes()).hexdigest() != sign['audit']['sha256']:
        Remote(remote_name).download(sign['signed_hap'], hap)
    if hashlib.sha256(hap.read_bytes()).hexdigest() != sign['audit']['sha256']:
        raise ValueError('signed package hash mismatch')
    verify_installable_profile(hap, case['host_app']['bundle_name'],
        ROOT/'toolchain/command-line-tools/sdk/default/openharmony/toolchains/lib/hap-sign-tool.jar')
    if hashlib.sha256(plan.read_bytes()).hexdigest() != capture['plan_sha256']:
        raise ValueError('workload changed since capture')
    repo = ROOT/case['host_app']['local_path']
    ref = app_ref(case, 'unfixed')
    tree = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', ref+'^{tree}'], text=True).strip()
    if tree != build['source']['tree'] or not build['source']['passed']:
        raise ValueError('source/build mismatch')
    if metric=='trace_cpu_ms':
        report=app_scheduler_report(capture_folder/'trace.htrace',capture,case['host_app']['bundle_name'])
    elif metric=='app_pss_bytes':
        report=app_memory_report(capture,case['host_app']['bundle_name'])
    else:
        report=app_report(json.loads((capture_folder/'report.json').read_text()), capture['pids'], case['host_app']['bundle_name'])
    # Refuse a pre-existing destination: stale fixed packages/receipts must not
    # survive in the diagnosis workspace. No git history is exported.
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'app.hap').write_bytes(hap.read_bytes())
    if include_source:
        subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar', '-o', str((destination/'app-source.tar').resolve()), ref], check=True)
    workload = json.loads(plan.read_text())
    workload['description'] = 'Application UI reproduction'
    (destination/'workload.json').write_text(json.dumps(workload, ensure_ascii=False, indent=2)+'\n')
    (destination/'reproduce.py').write_text(reproduction_script())
    (destination/'profile.json').write_text(json.dumps(report, ensure_ascii=False)+'\n')
    (destination/'symptom.txt').write_text(symptom+'\n')
    print(f'Exported app-only diagnosis data to {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    parser.add_argument('destination', type=Path)
    parser.add_argument('--symptom', required=True, help='observed user-facing symptom; no fix or oracle')
    parser.add_argument('--round', type=int, default=1)
    parser.add_argument('--remote', default='cityuPC')
    parser.add_argument('--include-source', action='store_true', help='explicit source-enabled diagnosis; excluded from binary-only blind evaluation')
    args = parser.parse_args()
    export(args.case, args.destination, args.symptom, args.round, args.remote, args.include_source)
