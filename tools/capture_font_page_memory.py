"""Collect kernel PSS during forty normal city-manager page visits."""
import hashlib,json
from pathlib import Path
from font_page_memory import verify_capture
ROOT=Path(__file__).resolve().parents[1]
CASE='sepweather_font_register_per_page'

def capture(remote,variant,number,revision='page-font-pss-v2'):
    base=ROOT/'artifacts/candidate-builds/font-page-v2';folder=base/revision/variant/f'round-{number}';folder.mkdir(parents=True,exist_ok=False)
    sign=json.loads((base/CASE/variant/'sign.json').read_text());installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
    if 'install bundle successfully' not in installed:raise ValueError(installed)
    for name in ('ui_driver.py','system_pss.py'):remote.upload(ROOT/'tools'/name,'/home/research/ohm-clean/tools/'+name)
    check={'op':'wait','selector':{'id':'AddAddressBtn','match':'exact'},'timeout_s':120}
    actions=[{'op':'tap','selector':{'id':'AddAddressBtn','match':'exact'}},{'op':'wait','selector':{'text':'城市管理','match':'exact'}},{'op':'wait','selector':{'text':'北京','match':'exact'}},{'op':'pause','seconds':0.5},{'op':'tap','selector':{'text':'\ue66a','match':'exact'}},check]
    plan={'bundle':'cn.seayj.sepweather','ability':'EntryAbility','description':'Open and return from the city manager','setup':[check,*actions,{'op':'pause','seconds':3}],'measured':[{'op':'repeat','count':40,'actions':actions}],'verify':[check]};(folder/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    target='/home/research/ohm-clean/font-page-v2/'+revision+'/'+variant+'/round-'+str(number)
    bundles=sorted({json.loads(p.read_text())['host_app']['bundle_name'] for p in (ROOT/'cases').glob('*/case.json')})
    code=r'''import hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
from ui_driver import UI
from system_pss import read_process,verify_window
root=Path(PAYLOAD['target']).resolve();root.mkdir(parents=True,exist_ok=False)
def shell(c):
 p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=120);assert p.returncode==0;return p.stdout
for name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):assert not shell('pidof '+name).strip()
assert shell('cat /sys/kernel/tracing/tracing_on').strip()=='0'
for bundle in PAYLOAD['bundles']:shell('aa force-stop '+bundle)
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
class Reader:
 def hdc(self,args):
  assert args[0]=='shell' and len(args)==2;return shell(args[1])
bundle='cn.seayj.sepweather';reader=Reader();ui=UI(shell,bundle,'EntryAbility');ui.run([{'op':'launch'}]);ui.run(PAYLOAD['plan']['setup']);pid=int(shell('pidof '+bundle).strip())
r={'status':'RUNNING','warmup_count':1,'snapshots':[],'steps':[],'frames':[],'pids':[pid]}
def snapshot(phase):
 start=time.monotonic();row=read_process(reader,pid,bundle);row.update(phase=phase,read_start_monotonic=start,monotonic=time.monotonic());r['snapshots'].append(row)
snapshot('before');r['action_start_monotonic']=time.monotonic()
try:
 actions=PAYLOAD['plan']['measured'][0]['actions']
 for index in range(40):
  ui.run(actions[:4]);layout=ui.layout();r['steps'].append({'number':index+1,'layout':layout})
  if index in (0,39):
   device='/data/local/tmp/font-frame-'+uuid.uuid4().hex+'.png';name='page-'+str(index+1)+'.png';shell('uitest screenCap -p '+device);subprocess.run(['hdc','file','recv',device,str(root/name)],check=True,capture_output=True);shell('rm -f '+device);r['frames'].append({'step':index+1,'file':name,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()})
  ui.run(actions[4:]);snapshot('workload');(root/'progress.json').write_text(json.dumps(r,ensure_ascii=False),encoding='utf8');print('STEP',index+1,flush=True)
 time.sleep(5);r['final_layout']=ui.layout();r['action_end_monotonic']=time.monotonic();snapshot('after');r['app_pss_bytes']=r['snapshots'][-1]['pss_bytes'];verify_window(r,bundle);r['status']='CAPTURED'
finally:(root/'capture.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
print(r['status'],r.get('app_pss_bytes'),flush=True)
'''
    print(remote.python(code,{'target':target,'plan':plan,'signed_hap':sign['signed_hap'],'signed_sha256':sign['audit']['sha256'],'bundles':bundles},timeout=900),flush=True)
    remote.download(target+'/capture.json',folder/'capture.json');record=json.loads((folder/'capture.json').read_text())
    for frame in record['frames']:remote.download(target+'/'+frame['file'],folder/frame['file'])
    record.update(case=CASE,variant=variant,round=number,measurement_revision=revision,metric='app_pss_bytes',signed_sha256=sign['audit']['sha256'],plan_sha256=hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest(),install_output=installed,reference_sha256=hashlib.sha256((ROOT/'validation/font-page-native-reference.json').read_bytes()).hexdigest(),performance_accepted=False)
    (folder/'capture.json').write_text(json.dumps(record,indent=2)+'\n');reference=json.loads((ROOT/'validation/font-page-native-reference.json').read_text());verify_capture(record,folder,reference);print(variant,record['app_pss_bytes'],flush=True);return record
