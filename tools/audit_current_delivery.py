"""Read-only audit of accepted binary deliveries; never launches device UI.

Raw performance acceptance is a separate verify_clean_cases complete-stage gate.
This audit checks current signatures, renewal identity, launch bindings, and the
five-file app-only exports against the accepted delivery manifest.
"""
import argparse
import ast
import hashlib
import json
import time
from pathlib import Path
from hap_profile_validity import verify_installable_profile
from reproduction_hap_identity import verify_identity
ROOT=Path(__file__).resolve().parents[1]
FILES={'app.hap','profile.json','reproduce.py','symptom.txt','workload.json'}

def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def audit(expected):
    manifest_path=ROOT/'validation/accepted-current-reproduction-delivery.json';manifest_hash=digest(manifest_path);manifest=json.loads(manifest_path.read_text())
    accepted={p.parent.name:p for p in (ROOT/'cases').glob('*/case.json') if json.loads(p.read_text())['test_oracle'].get('evidence',{}).get('status')=='measured_clean'}
    if (len(accepted)!=expected or len(manifest['rows'])!=expected or {r['case'] for r in manifest['rows']}!=set(accepted) or manifest['cases']!=expected or manifest['variants']!=2*expected or manifest['binary_only_agent_exports']!=expected):
        raise ValueError('accepted case inventory and delivery manifest differ')
    tool=ROOT/'toolchain/command-line-tools/sdk/default/openharmony/toolchains/lib/hap-sign-tool.jar';rows=[]
    for row in manifest['rows']:
        cid=row['case'];case_path=accepted[cid];case_hash=digest(case_path);case=json.loads(case_path.read_text());bundle=case['host_app']['bundle_name'];proof=ROOT/row['case_proof']
        if (digest(proof)!=row['case_proof_sha256'] or case['reproduction_delivery']['status']!='PASS' or case['reproduction_delivery']['proof']!=row['case_proof'] or case.get('disposition',{}).get('status')=='skipped_by_user'):
            raise ValueError('accepted delivery proof changed: '+cid)
        variants={}
        for variant,record in row['variants'].items():
            if variant not in ('unfixed','fixed'):raise ValueError('unknown delivered variant')
            measured=ROOT/'artifacts/clean'/cid/variant;original=json.loads((measured/'sign.json').read_text())
            if original['audit']['sha256']!=record['measured_signed_sha256'] or digest(measured/'app-export.hap')!=record['measured_signed_sha256']:
                raise ValueError('historical measured package changed: '+cid)
            renewed=record['signed_sha256']!=record['measured_signed_sha256']
            current=ROOT/'artifacts/reproduction-signatures'/cid/variant if renewed else measured
            sign=json.loads((current/'sign.json').read_text());hap=current/'app-export.hap'
            if sign['status']!='PASS' or sign['audit']['sha256']!=record['signed_sha256'] or digest(hap)!=record['signed_sha256']:
                raise ValueError('current delivery differs from signed package: '+cid)
            if renewed:
                identity=verify_identity(measured/'app-unsigned.hap',measured/'app-export.hap',hap,bundle,tool)
                if digest(current/'identity.json')!=record['identity_receipt_sha256'] or identity['renewed_signed_sha256']!=record['signed_sha256']:
                    raise ValueError('renewal identity receipt changed: '+cid)
                validity=identity['renewed_profile_validity'];launch=current/'smoke.json'
            else:
                validity=verify_installable_profile(hap,bundle,tool)
                if record.get('fresh_launch_evidence'):launch=ROOT/record['fresh_launch_evidence']
                elif cid=='wanharmony_persisted_home_list_growth':launch=ROOT/'artifacts/hkrc-delivery'/cid/variant/'smoke.json'
                else:raise ValueError('explicit current launch evidence is missing: '+cid)
            if digest(launch)!=record['fresh_launch_receipt_sha256']:raise ValueError('launch evidence changed: '+cid)
            receipt=json.loads(launch.read_text())
            if receipt.get('signed_sha256')!=record['signed_sha256']:raise ValueError('launch used another signed binary: '+cid)
            if launch.name=='smoke.json' and (receipt['status']!='PASS' or receipt['foreground_bundle']!=bundle or not receipt['pids']):raise ValueError('foreground launch is not proven: '+cid)
            variants[variant]={'signed_sha256':record['signed_sha256'],'measured_signed_sha256':record['measured_signed_sha256'],'current_validity':validity,'renewal_identity_recomputed':renewed,'launch_path':str(launch.relative_to(ROOT)),'launch_sha256':digest(launch)}
        if set(variants)!={'unfixed','fixed'}:raise ValueError('both delivered variants are required')
        folder=ROOT/row['agent_export']
        if {p.name for p in folder.iterdir()}!=FILES or set(row['agent_files_sha256'])!=FILES:raise ValueError('binary-only delivery file set changed: '+cid)
        for name in FILES:
            p=folder/name
            if digest(p)!=row['agent_files_sha256'][name]:raise ValueError('agent export changed: '+cid+'/'+name)
            if name!='app.hap':
                contents=p.read_text()
                for token in (cid,'ohm-clean','fixture_sha256','paired_ratios','marker_token'):
                    if token in contents:raise ValueError('evaluator metadata appears in agent export: '+cid+'/'+name)
        if row['agent_files_sha256']['app.hap']!=variants['unfixed']['signed_sha256']:raise ValueError('agent did not receive the current unfixed app')
        workload=json.loads((case_path.parent/case['testcase']['workload']).read_text());workload['description']='Application UI reproduction'
        if json.loads((folder/'workload.json').read_text())!=workload:raise ValueError('agent workload differs from the accepted ordinary UI path')
        ast.parse((folder/'reproduce.py').read_text());profile=json.loads((folder/'profile.json').read_text())
        if not profile.get('processNameMap') or set(profile['processNameMap'].values())!={bundle}:raise ValueError('exported profile is not app-only')
        if digest(case_path)!=case_hash:raise ValueError('case changed during read-only delivery audit')
        rows.append({'case':cid,'case_sha256':case_hash,'proof_sha256':digest(proof),'variants':variants,'agent_files_sha256':row['agent_files_sha256']})
        print('DELIVERY VERIFIED',cid,flush=True)
    if digest(manifest_path)!=manifest_hash:raise ValueError('delivery manifest changed during audit; rerun on the completed inventory')
    return {'status':'CURRENT_DELIVERIES_REVALIDATED','cases':expected,'variants':2*expected,'checked_at':time.time(),'manifest_sha256':manifest_hash,'raw_performance_revalidated_by_this_tool':False,'rows':rows}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expected',type=int,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();result=audit(args.expected);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(result['status'],result['cases'])
