#!/usr/bin/env python3
"""Resume only the verified pre-UI short-page rejection of the original trial.

Keeps completed pages and every failed artifact, verifies the same live app
process/file, and resumes at the rejected page without a UI or data reset.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid
import zipfile

from collect_wan_home_write_pages import SETUP_CODE,CYCLE_CODE
from install_wan_home_cache_fixture import install
from native_file_writes import returned_file_writes
from remote_device import Remote
from system_pss import start_ticks
from wan_home_write_cycle import PREFERENCES,verify_backend_page


def resume(proof_path):
    proof_path=Path(proof_path);proof=json.loads(proof_path.read_text());cid=proof['case']
    if cid!='wanharmony_persisted_home_list_growth' or set(proof['variants'])!={'unfixed'}:
        raise ValueError('this resume is restricted to the original unfixed pre-UI rejection')
    row=proof['variants']['unfixed'];failed=row['cycles'][-1];folder=Path(failed['raw_artifacts'])
    receipt=json.loads((folder/'result.json').read_text())
    if failed['status']!='FAIL' or 'before' in receipt or 'capture' in receipt:
        raise ValueError('failed attempt may have changed UI or recorded app work; inspect manually')
    sampled=json.loads((folder/'backend.json').read_bytes());verify_backend_page(sampled,failed['page'])
    if not 1<=len(sampled['data']['datas'])<10:
        raise ValueError('not the observed successful short public page')
    prior_folder=Path(row['cycles'][-2]['raw_artifacts']);prior=json.loads((prior_folder/'result.json').read_text())['capture']['action']['after']
    r=Remote()
    for name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):
        if r.hdc(['shell','pidof '+name]).strip():raise ValueError('original profiler is live; do not alter it')
    if r.hdc(['shell','cat /sys/kernel/tracing/tracing_on']).strip()!='0':raise ValueError('original trace is live')
    verified=r.python('''import subprocess,sys,hashlib
sys.path.insert(0,'/home/research/ohm-clean/tools')
from system_pss import start_ticks
pid=PAYLOAD['pid'];p=subprocess.run(['hdc','shell','cat /proc/'+str(pid)+'/stat'],capture_output=True,text=True,timeout=30)
assert start_ticks(p.stdout,pid)==start_ticks(PAYLOAD['stat'],pid)
p=subprocess.run(['hdc','shell','pidof org.example.wan.ohos'],capture_output=True,text=True,timeout=30);assert p.stdout.strip()==str(pid)
p=subprocess.run(['hdc','shell','cat '+PAYLOAD['preferences']],capture_output=True,timeout=60);assert hashlib.sha256(p.stdout).hexdigest()==PAYLOAD['sha256']
print('SAME_ORIGINAL_PROCESS_AND_FILE_VERIFIED')
''',{'pid':prior['pid'],'stat':prior['stat'],'preferences':PREFERENCES,'sha256':prior['preferences_sha256']},timeout=120).strip()
    if verified!='SAME_ORIGINAL_PROCESS_AND_FILE_VERIFIED':raise ValueError('original app state is not verified')
    archive=Path(row['raw_artifacts'])/('proof-before-resume-'+uuid.uuid4().hex+'.json');archive.write_bytes(proof_path.read_bytes());archive.chmod(0o600)
    row.setdefault('failed_attempts',[]).append(row['cycles'].pop())
    event={'reason':'Successful public page has fewer returned rows than requested maximum 10; original rejection occurred before any device action.',
           'resume_page':failed['page'],'actual_server_rows':len(sampled['data']['datas']),
           'original_proof_snapshot':str(archive),'original_proof_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
           'same_original_app_state_verified':True,'new_collector_sha256':hashlib.sha256(Path('tools/wan_home_write_cycle.py').read_bytes()).hexdigest()}
    proof.setdefault('resume_events',[]).append(event)
    proof['collection_process']={'pid':os.getpid(),'stat':Path('/proc/self/stat').read_text()}
    proof_path.write_text(json.dumps(proof,indent=2)+'\n')
    r.upload(Path('tools/wan_home_write_cycle.py'),'/home/research/ohm-clean/tools/wan_home_write_cycle.py')
    case=json.loads((Path('cases')/cid/'case.json').read_text())
    for variant in ('unfixed','fixed'):
        if variant=='fixed':
            token=uuid.uuid4().hex;root='/home/research/ohm-clean/wan-home-ten-page/'+token
            local=Path('artifacts/clean')/cid/variant/'ten-page-filesystem'/token;local.mkdir(parents=True,exist_ok=False,mode=0o700)
            sign=json.loads((Path('artifacts/clean')/cid/variant/'sign.json').read_text())
            r.python('from pathlib import Path\nimport hashlib\nassert hashlib.sha256(Path(PAYLOAD["hap"]).read_bytes()).hexdigest()==PAYLOAD["sha"]',{'hap':sign['signed_hap'],'sha':sign['audit']['sha256']})
            installed=r.hdc(['install','-r',sign['signed_hap']],timeout=180)
            if 'install bundle successfully' not in installed:raise ValueError('fixed package install failed')
            prep=install(r,case,Path('artifacts/fixtures/wan-home-cache'),PREFERENCES)
            print('SETUP',variant,r.python(SETUP_CODE,{'root':root,'variant':variant},timeout=240),flush=True)
            r.download(root+'/setup.json',local/'setup.json');setup=json.loads((local/'setup.json').read_text())
            row={'status':setup['status'],'raw_artifacts':str(local),'remote_root':root,'signed_sha256':sign['audit']['sha256'],'install_output':installed,'preparation':prep,'cycles':[]}
            proof['variants'][variant]=row;proof_path.write_text(json.dumps(proof,indent=2)+'\n')
            if setup['status']!='ORIGINAL_FIXTURE_NORMAL_FIRST_PAGE_READY':raise ValueError('inspect original fixed setup failure')
        else:
            row=proof['variants'][variant];root=row['remote_root'];local=Path(row['raw_artifacts'])
        for page in range(len(row['cycles'])+1,11):
            suffix='page-'+str(page)+'-'+uuid.uuid4().hex
            cycle_root=root+'/'+suffix;cycle_local=local/suffix;remote_zip=cycle_root+'.zip'
            print('CYCLE',variant,page,r.python(CYCLE_CODE,{'root':cycle_root,'page':page,'variant':variant,'archive':remote_zip},timeout=420),flush=True)
            local_zip=local/(suffix+'.zip');r.download(remote_zip,local_zip);local_zip.chmod(0o600);cycle_local.mkdir(mode=0o700)
            with zipfile.ZipFile(local_zip) as bundle:
                if any(Path(n).is_absolute() or '..' in Path(n).parts for n in bundle.namelist()):raise ValueError('invalid native archive member')
                bundle.extractall(cycle_local)
            for path in cycle_local.rglob('*'):path.chmod(0o700 if path.is_dir() else 0o600)
            result=json.loads((cycle_local/'result.json').read_text());cap=result.get('capture',{})
            cycle={'page':page,'status':result['status'],'error':result.get('error'),'raw_artifacts':str(cycle_local),
                   'receipt_sha256':hashlib.sha256((cycle_local/'result.json').read_bytes()).hexdigest(),
                   'archive_sha256':hashlib.sha256(local_zip.read_bytes()).hexdigest()}
            if result['status']=='ONE_NORMAL_PAGE_NATIVE_FILE_TRACE_CAPTURED_AUDIT_PENDING':
                raw=(cycle_local/'capture/trace.txt').read_bytes()
                if hashlib.sha256(raw).hexdigest()!=cap['trace_sha256']:raise ValueError('original trace bytes changed')
                targets=[]
                for state in (result['before'],cap['action']['after']):
                    fields=state['file_identity'].split();dev,ino=map(int,fields[:2]);targets.append((dev>>20,dev&((1<<20)-1),ino))
                traffic=returned_file_writes(raw.decode(),targets)
                cycle.update(retention=cap['retention'],native_progress=cap['action']['progress'],selected_endpoint_inode_file_bytes=traffic['returned_bytes'],file_traffic=traffic,complete_persistence_traffic_verified=False,exclusive_home_list_bytes_verified=False)
            row['cycles'].append(cycle);proof_path.write_text(json.dumps(proof,indent=2)+'\n')
            print('CYCLE_RETAINED',variant,page,cycle['status'],cycle.get('selected_endpoint_inode_file_bytes'),flush=True)
            if result['status']!='ONE_NORMAL_PAGE_NATIVE_FILE_TRACE_CAPTURED_AUDIT_PENDING' or cap.get('cleanup_error'):
                raise ValueError('inspect the original failed cycle before more UI: '+str(result.get('error')))
        row['status']='TEN_NORMAL_NEW_PAGES_CAPTURED_NATIVE_MECHANISM_AUDIT_PENDING';proof_path.write_text(json.dumps(proof,indent=2)+'\n')
    proof['status']='BOTH_VARIANTS_TEN_NORMAL_NEW_PAGES_CAPTURED_NATIVE_MECHANISM_AUDIT_PENDING';proof_path.write_text(json.dumps(proof,indent=2)+'\n')
    print('TEN_PAGE_FILESYSTEM_TERMINAL',proof['status'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('proof',type=Path);args=parser.parse_args();resume(args.proof)
