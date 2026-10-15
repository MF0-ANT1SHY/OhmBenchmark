#!/usr/bin/env python3
"""Verify separately prepared reproduction signatures and a binary-only agent export.

Run only while this process has exclusive ownership of device UI operations.
Historical measurements remain immutable. Each case is committed by the caller.
"""
import argparse
import hashlib
import json
import uuid
from pathlib import Path

from remote_device import Remote
from prepare_reproduction_signature import prepare
from smoke_clean_cases import smoke
from export_agent_data import export, require_accepted_case

ROOT = Path(__file__).resolve().parents[1]


def verify(remote, cid, symptom):
    if not symptom.strip():
        raise ValueError('a neutral user-visible symptom is required')
    r=remote
    case_path=ROOT/'cases'/cid/'case.json'
    case=json.loads(case_path.read_text())
    require_accepted_case(cid,case,1)
    root=ROOT/'artifacts/reproduction-signatures'
    for name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):assert not r.hdc(['shell','pidof '+name]).strip()
    assert r.hdc(['shell','cat /sys/kernel/tracing/tracing_on']).strip()=='0'
    main=ROOT/'artifacts/clean'/cid
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for v in ('unfixed','fixed') for p in (main/v).iterdir() if p.is_file() and p.name in ('build.json','sign.json','smoke.json','performance.json','app-export.hap','app-unsigned.hap')}
    variants={}
    for variant in ('unfixed','fixed'):
     identity=prepare(r,cid,variant);smoke(r,case,variant,root)
     receipt=json.loads((root/cid/variant/'smoke.json').read_text());assert receipt['status']=='PASS' and receipt['signed_sha256']==identity['renewed_signed_sha256']
     variants[variant]={'status':'PASS','business_and_provisioning_identity_verified':True,'signed_sha256':receipt['signed_sha256'],'launch_receipt':receipt}
    folder=ROOT/'artifacts/agent-exports'/('current-'+uuid.uuid4().hex)
    export(cid,folder,symptom,1)
    expected={'app.hap','profile.json','reproduce.py','symptom.txt','workload.json'};assert {p.name for p in folder.iterdir()}==expected
    assert hashlib.sha256((folder/'app.hap').read_bytes()).hexdigest()==variants['unfixed']['signed_sha256']
    for p in folder.iterdir():
     if p.name=='app.hap':continue
     for token in (cid,'ohm-clean','marker_token','fixture_sha256','paired_ratios'):assert token not in p.read_text(),(p.name,token)
    assert before=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
    proof={'case':cid,'status':'PASS','scope':'Current reproduction delivery only; historical performance evidence unchanged','variants':variants,'binary_only_export':str(folder),'files':sorted(expected),'main_artifacts_unchanged':True,'new_performance_measurement_claimed':False}
    output=ROOT/'validation'/(cid+'-current-reproduction-delivery.json');output.write_text(json.dumps(proof,indent=2)+'\n')
    case['reproduction_delivery']={'status':'PASS','proof':str(output.relative_to(ROOT)),'business_identity_preserved':True,'current_signature_launch_verified':True,'binary_only_export_verified':True,'historical_performance_evidence_unchanged':True}
    case_path.write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    parser.add_argument('--symptom',required=True)
    args=parser.parse_args()
    result=verify(Remote(),args.case,args.symptom)
    print(args.case,result['status'],flush=True)
