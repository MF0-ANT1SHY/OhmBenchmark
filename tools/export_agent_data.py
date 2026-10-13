#!/usr/bin/env python3
"""Export business-only unfixed sources and app-scoped system samples.

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

ROOT = Path(__file__).resolve().parents[1]


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


def export(cid, destination, symptom, round_number, remote_name='cityuPC', include_source=False):
    case = json.loads((ROOT/'cases'/cid/'case.json').read_text())
    folder = ROOT/'artifacts/clean'/cid/'unfixed'
    build = json.loads((folder/'build.json').read_text())
    sign = json.loads((folder/'sign.json').read_text())
    capture_folder = folder/'cpu-captures'/f'round-{round_number}'
    capture = json.loads((capture_folder/'capture.json').read_text())
    hap = folder/'app-export.hap'
    plan = ROOT/'cases'/cid/case['testcase']['workload']
    if sign['status'] != 'PASS' or not sign['audit']['passed'] or capture['status'] != 'CAPTURED' or capture['signed_sha256'] != sign['audit']['sha256']:
        raise ValueError('unmatched capture/package')
    if not hap.exists() or hashlib.sha256(hap.read_bytes()).hexdigest() != sign['audit']['sha256']:
        Remote(remote_name).download(sign['signed_hap'], hap)
    if hashlib.sha256(hap.read_bytes()).hexdigest() != sign['audit']['sha256']:
        raise ValueError('signed package hash mismatch')
    if hashlib.sha256(plan.read_bytes()).hexdigest() != capture['plan_sha256']:
        raise ValueError('workload changed since capture')
    repo = ROOT/case['host_app']['local_path']
    ref = app_ref(case, 'unfixed')
    tree = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', ref+'^{tree}'], text=True).strip()
    if tree != build['source']['tree'] or not build['source']['passed']:
        raise ValueError('source/build mismatch')
    report = app_report(json.loads((capture_folder/'report.json').read_text()), capture['pids'], case['host_app']['bundle_name'])
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
