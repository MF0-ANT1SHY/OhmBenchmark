#!/usr/bin/env python3
"""Collect both original-fixture Wan ten-page native filesystem trials.

Run from the repository root. Existing output refuses a new run; inspect or
resume the actual original job instead of restarting after an observation timeout.
This emits raw mechanism data only and cannot accept a performance case.
"""
import argparse,sys,json,uuid,hashlib,zipfile
from pathlib import Path
sys.path.insert(0,'tools')
from remote_device import Remote
from install_wan_home_cache_fixture import install,fixture_state
from native_file_writes import returned_file_writes

SETUP_CODE = '''import sys,json,time,subprocess
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools')
from ui_driver import UI
from wan_home_write_cycle import backend,observe
root=Path(PAYLOAD['root']);root.mkdir(parents=True,exist_ok=False,mode=0o700)
def shell(cmd):
 p=subprocess.run(['hdc','shell',cmd],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
ui=UI(shell,'org.example.wan.ohos','EntryAbility');result={'status':'FAIL','performance_accepted':False}
try:
 source=backend(0,root);result['backend']=source;expected=[row['id'] for row in source['rows']];shell('power-shell wakeup');ui.run([{'op':'launch'},{'op':'wait','selector':{'text':'首页'}}]);deadline=time.monotonic()+90
 while True:
  state=observe(ui,root,'setup-'+str(time.time_ns()));result['observation']=state;key='homeList' if PAYLOAD['variant']=='unfixed' else 'homeListCache';logs=state['native_log_receipt']['raw_logs']
  successful=sum('/network: (200) response:' in line for line in logs.splitlines())
  if state['ids'][key]==expected and successful>=3:break
  if time.monotonic()>deadline:raise RuntimeError('normal first page and all three startup APIs did not complete')
  time.sleep(.5)
 result['layout']=ui.layout();result['status']='ORIGINAL_FIXTURE_NORMAL_FIRST_PAGE_READY'
except Exception as exc:
 result['error']=str(exc)
 try:result['failure_layout']=ui.layout()
 except Exception:pass
(root/'setup.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(root/'setup.json').chmod(0o600);print(json.dumps({'status':result['status'],'error':result.get('error')}))
'''

CYCLE_CODE = '''import sys,json,subprocess,zipfile
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools')
from ui_driver import UI
from wan_home_write_cycle import collect
root=Path(PAYLOAD['root'])
def shell(cmd):
 p=subprocess.run(['hdc','shell',cmd],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
result=collect(UI(shell,'org.example.wan.ohos','EntryAbility'),root,PAYLOAD['page'],PAYLOAD['variant'])
with zipfile.ZipFile(PAYLOAD['archive'],'x',compression=zipfile.ZIP_STORED) as bundle:
 for path in root.rglob('*'):
  if path.is_file():bundle.write(path,path.relative_to(root))
Path(PAYLOAD['archive']).chmod(0o600);print(json.dumps({'status':result['status'],'error':result.get('error')}))
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('validation/wan-home-ten-page-native-filesystem.json'))
    args=parser.parse_args()
    r=Remote();cid='wanharmony_persisted_home_list_growth';case=json.loads((Path('cases')/cid/'case.json').read_text());fixture=Path('artifacts/fixtures/wan-home-cache');fixture_state(fixture);prefs='/data/app/el2/100/base/org.example.wan.ohos/haps/entry/files/persistent_storage';proof_path=args.output
    if proof_path.exists():raise FileExistsError('Inspect the existing trial; never restart based on observation timeout')
    proof={'case':cid,'status':'TEN_PAGE_FILESYSTEM_COLLECTION_IN_PROGRESS','app_injection':False,'performance_accepted':False,'original_fixture_articles':471,'variants':{}}
    for name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):assert not r.hdc(['shell','pidof '+name]).strip()
    assert r.hdc(['shell','cat /sys/kernel/tracing/tracing_on']).strip()=='0'
    for name in ('wan_home_write_cycle.py','audit_wan_home_primary.py','install_wan_home_cache_fixture.py','seed_wan_home_cache.py','native_hilog.py','native_file_trace.py','native_file_writes.py','native_trace_record.py','rss_refresh_progress.py','system_pss.py','ui_driver.py','wan_html_inputs.py'):r.upload(Path('tools')/name,'/home/research/ohm-clean/tools/'+name)
    for variant in ('unfixed','fixed'):
     token=uuid.uuid4().hex;root='/home/research/ohm-clean/wan-home-ten-page/'+token;local=Path('artifacts/clean')/cid/variant/'ten-page-filesystem'/token;local.mkdir(parents=True,mode=0o700,exist_ok=False);sign=json.loads((Path('artifacts/clean')/cid/variant/'sign.json').read_text())
     r.python('from pathlib import Path\nimport hashlib\np=Path(PAYLOAD["hap"]);assert hashlib.sha256(p.read_bytes()).hexdigest()==PAYLOAD["sha"]',{'hap':sign['signed_hap'],'sha':sign['audit']['sha256']})
     installed=r.hdc(['install','-r',sign['signed_hap']],timeout=180);assert 'install bundle successfully' in installed
     prep=install(r,case,fixture,prefs);assert prep['articles']==471
     setup=SETUP_CODE
     print('SETUP',variant,r.python(setup,{'root':root,'variant':variant},timeout=240),flush=True);r.download(root+'/setup.json',local/'setup.json');initial=json.loads((local/'setup.json').read_text());row={'status':initial['status'],'raw_artifacts':str(local),'remote_root':root,'signed_sha256':sign['audit']['sha256'],'install_output':installed,'preparation':prep,'cycles':[]};proof['variants'][variant]=row;proof_path.write_text(json.dumps(proof,indent=2)+'\n')
     if initial['status']!='ORIGINAL_FIXTURE_NORMAL_FIRST_PAGE_READY':raise RuntimeError('Inspect saved initial business state: '+str(initial.get('error')))
     for page in range(1,11):
      cycle_root=root+'/page-'+str(page);cycle_local=local/('page-'+str(page));archive=root+'/page-'+str(page)+'.zip'
      code=CYCLE_CODE
      print('CYCLE',variant,page,r.python(code,{'root':cycle_root,'page':page,'variant':variant,'archive':archive},timeout=420),flush=True)
      archive_local=local/('page-'+str(page)+'.zip');r.download(archive,archive_local);archive_local.chmod(0o600);cycle_local.mkdir(mode=0o700)
      with zipfile.ZipFile(archive_local) as bundle:
       for name in bundle.namelist():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('invalid native archive member')
       bundle.extractall(cycle_local)
      for path in cycle_local.rglob('*'):path.chmod(0o700 if path.is_dir() else 0o600)
      result=json.loads((cycle_local/'result.json').read_text());cap=result.get('capture',{});cycle={'page':page,'status':result['status'],'error':result.get('error'),'raw_artifacts':str(cycle_local),'receipt_sha256':hashlib.sha256((cycle_local/'result.json').read_bytes()).hexdigest(),'archive_sha256':hashlib.sha256(archive_local.read_bytes()).hexdigest()}
      if result['status']=='ONE_NORMAL_PAGE_NATIVE_FILE_TRACE_CAPTURED_AUDIT_PENDING':
       trace=(cycle_local/'capture/trace.txt').read_bytes();assert hashlib.sha256(trace).hexdigest()==cap['trace_sha256'];targets=[]
       for rec in (result['before'],cap['action']['after']):
        fields=rec['file_identity'].split();dev,ino=map(int,fields[:2]);targets.append((dev>>20,dev&((1<<20)-1),ino))
       traffic=returned_file_writes(trace.decode(),targets);cycle.update(retention=cap['retention'],native_progress=cap['action']['progress'],selected_endpoint_inode_file_bytes=traffic['returned_bytes'],file_traffic=traffic,complete_persistence_traffic_verified=False,exclusive_home_list_bytes_verified=False)
      row['cycles'].append(cycle);proof_path.write_text(json.dumps(proof,indent=2)+'\n');print('CYCLE_RETAINED',variant,page,cycle['status'],cycle.get('selected_endpoint_inode_file_bytes'),flush=True)
      if result['status']!='ONE_NORMAL_PAGE_NATIVE_FILE_TRACE_CAPTURED_AUDIT_PENDING' or cap.get('cleanup_error'):raise RuntimeError('Inspect the original failed cycle before more UI: '+str(result.get('error',cap.get('cleanup_error'))))
     row['status']='TEN_NORMAL_NEW_PAGES_CAPTURED_NATIVE_MECHANISM_AUDIT_PENDING';proof_path.write_text(json.dumps(proof,indent=2)+'\n')
    proof['status']='BOTH_VARIANTS_TEN_NORMAL_NEW_PAGES_CAPTURED_NATIVE_MECHANISM_AUDIT_PENDING';proof_path.write_text(json.dumps(proof,indent=2)+'\n');print('TEN_PAGE_FILESYSTEM_TERMINAL',proof['status'],flush=True)


if __name__ == '__main__':
    main()
