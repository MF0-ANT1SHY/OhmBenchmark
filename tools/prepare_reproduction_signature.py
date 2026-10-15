#!/usr/bin/env python3
"""Prepare an equivalent current signature, without installing or querying a device.

Retain the cryptographically verified measured UDID binding. Historical package,
signature and performance receipts are never replaced. Fresh launch is separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import uuid

from export_agent_data import require_accepted_case
from hap_profile_validity import read_signed_profile, verify_profile, ExpiredProfileError
from remote_device import Remote
from reproduction_hap_identity import verify_identity

ROOT = Path(__file__).resolve().parents[1]
SIGN_TOOL = ROOT/'toolchain/command-line-tools/sdk/default/openharmony/toolchains/lib/hap-sign-tool.jar'


def prepare(remote, cid, variant='unfixed'):
    if variant not in ('unfixed','fixed'):
        raise ValueError('reproduction signature variant must be unfixed or fixed')
    case = json.loads((ROOT/'cases'/cid/'case.json').read_text())
    require_accepted_case(cid,case,1)
    base = ROOT/'artifacts/clean'/cid/variant
    build = json.loads((base/'build.json').read_text())
    measured_sign = json.loads((base/'sign.json').read_text())
    unsigned = base/'app-unsigned.hap'
    if (build['status'] != 'PASS' or not build['hap']['passed'] or
            hashlib.sha256(unsigned.read_bytes()).hexdigest() != build['hap']['sha256'] or
            measured_sign['unsigned_sha256'] != build['hap']['sha256']):
        raise ValueError('audited measured business build is not proven')
    measured = base/'app-export.hap'
    if not measured.exists():remote.download(measured_sign['signed_hap'],measured)
    if hashlib.sha256(measured.read_bytes()).hexdigest() != measured_sign['audit']['sha256']:
        raise ValueError('cached measured HAP differs; preserve and investigate it')
    profile, _ = read_signed_profile(measured,SIGN_TOOL)
    bundle = case['host_app']['bundle_name']
    try:
        verify_profile(profile,bundle)
        return {'case':cid,'variant':variant,'status':'MEASURED_SIGNATURE_CURRENT_RENEWAL_NOT_REQUIRED'}
    except ExpiredProfileError:
        pass
    ids = profile.get('debug-info',{}).get('device-ids',[])
    if len(ids) != 1:
        raise ValueError('retain exactly the measured debug-device binding, not a guessed replacement')
    folder = ROOT/'artifacts/reproduction-signatures'/cid/variant
    if folder.exists():
        if not all((folder/name).is_file() for name in ('app-export.hap','sign.json','identity.json')):
            raise ValueError('incomplete existing preparation must be preserved before retrying')
        existing = json.loads((folder/'sign.json').read_text())
        if (existing.get('status') != 'PASS' or not existing.get('audit',{}).get('passed') or
                existing['audit']['sha256'] != hashlib.sha256((folder/'app-export.hap').read_bytes()).hexdigest() or
                existing.get('unsigned_sha256') != build['hap']['sha256']):
            raise ValueError('existing reproduction signature metadata does not match its package/build')
        result = verify_identity(unsigned,measured,folder/'app-export.hap',bundle,SIGN_TOOL)
        result.update(case=cid,variant=variant,existing_preparation_rechecked=True,live_device_queries_performed=False)
        return result
    folder.mkdir(parents=True,exist_ok=False)
    for name in ('build.json','app-unsigned.hap'):shutil.copy2(base/name,folder/name)
    originals = {name:hashlib.sha256((base/name).read_bytes()).hexdigest()
                 for name in ('sign.json','performance.json','app-export.hap','app-unsigned.hap')}
    root = f'/home/research/ohm-clean/reproduction-signatures-{uuid.uuid4().hex}/{cid}/{variant}'
    remote.upload(ROOT/'tools/sdk_signing.py','/home/research/ohm-clean/tools/sdk_signing.py')
    remote.upload(ROOT/'tools/audit_clean_app.py','/home/research/ohm-clean/tools/audit_clean_app.py')
    remote.upload(unsigned,root+'/app-unsigned.hap')
    code = """import hashlib,importlib.util,json,os,sys
from pathlib import Path
os.environ['PATH']='/home/research/.local/bin:'+os.environ['PATH']
sys.path.insert(0,'/home/research/ohm-clean/tools')
from audit_clean_app import audit_hap
root=Path(PAYLOAD['root']);unsigned=root/'app-unsigned.hap';signed=root/'app.hap'
assert hashlib.sha256(unsigned.read_bytes()).hexdigest()==PAYLOAD['unsigned_sha256']
spec=importlib.util.spec_from_file_location('signing','/home/research/ohm-clean/tools/sdk_signing.py')
signing=importlib.util.module_from_spec(spec);spec.loader.exec_module(signing)
signing.sign(str(unsigned),str(signed),PAYLOAD['bundle'],device_udid=PAYLOAD['measured_device_id'],measured_profile=PAYLOAD['measured_profile'])
audit=audit_hap(signed,Path('/home/research/OhmBenchmark-toolchain/command-line-tools/sdk/default/openharmony/toolchains/ark_disasm'))
assert audit['passed']
record={'case':PAYLOAD['case'],'variant':PAYLOAD['variant'],'unsigned_sha256':PAYLOAD['unsigned_sha256'],
        'signed_hap':str(signed),'audit':audit,'status':'PASS'}
(root/'sign.json').write_text(json.dumps(record,indent=2)+'\\n')
"""
    remote.python(code,dict(root=root,unsigned_sha256=build['hap']['sha256'],bundle=bundle,
                           case=cid,variant=variant,measured_device_id=ids[0],measured_profile=profile),timeout=600)
    remote.download(root+'/sign.json',folder/'sign.json')
    remote.download(root+'/app.hap',folder/'app-export.hap')
    sign = json.loads((folder/'sign.json').read_text())
    if hashlib.sha256((folder/'app-export.hap').read_bytes()).hexdigest() != sign['audit']['sha256']:
        raise ValueError('renewed signed transfer hash mismatch')
    result = verify_identity(unsigned,measured,folder/'app-export.hap',bundle,SIGN_TOOL)
    if originals != {name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in originals}:
        raise ValueError('historical measurement artifact changed during separate signing')
    result.update(case=cid,variant=variant,main_artifacts_unchanged=True,reproduction_artifacts=str(folder),
                  sign_receipt=sign,live_device_queries_performed=False)
    (folder/'identity.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('cases',nargs='+')
    parser.add_argument('--variant',choices=['unfixed','fixed','both'],default='unfixed')
    args=parser.parse_args();remote=Remote()
    for cid in args.cases:
        for variant in (('unfixed','fixed') if args.variant=='both' else (args.variant,)):
            result=prepare(remote,cid,variant)
            print(cid,variant,result['status'],flush=True)
