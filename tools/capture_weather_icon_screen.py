"""Pixel-complete native cold-launch screen; not final acceptance by itself."""
import hashlib,json
from pathlib import Path
from remote_device import Remote
from weather_service_fixture import prepare,same_instance
from weather_icon_pixels import matches,icon_boxes
ROOT=Path(__file__).resolve().parents[1]
CASE='weatherassistant_remote_weather_icons'
BUNDLE='com.alatus.futureweather'


def capture(remote,variant,namespace='image-screen-v1'):
    base=ROOT/'artifacts/candidate-builds/weather-icons-v2';folder=base/namespace/variant;folder.mkdir(parents=True,exist_ok=False)
    reference=json.loads((ROOT/'validation/weather-icons-native-reference.json').read_text());sign=json.loads((base/CASE/variant/'sign.json').read_text())
    before=prepare(remote,base/CASE/'fixed/app-export.hap')
    installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
    if 'install bundle successfully' not in installed:raise ValueError(installed)
    remote.upload(ROOT/'tools/weather_icon_pixels.py','/home/research/ohm-clean/tools/weather_icon_pixels.py')
    target='/home/research/ohm-clean/weather-icons-v2/'+namespace+'/'+variant
    code=r'''import hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/venvs/image/Lib/site-packages').resolve()))
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
from weather_icon_pixels import matches,icon_boxes,BUNDLE
from ui_driver import UI
subprocess.run(['hdc','rport','tcp:18492','tcp:18492'],check=True,capture_output=True)
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
def shell(c):
 p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=120);assert p.returncode==0;return p.stdout
root=Path(PAYLOAD['target']).resolve();root.mkdir(parents=True,exist_ok=False);ui=UI(shell,BUNDLE,'AlatusAbility')
shell('aa force-stop '+BUNDLE);clean=shell('bm clean -n '+BUNDLE+' -c');assert 'success' in clean.lower(),clean
shell('power-shell wakeup');shell('uitest uiInput swipe 630 2300 630 500 600')
def snapshot(name):
 device='/data/local/tmp/weather-frame-'+uuid.uuid4().hex+'.png';start=time.monotonic();result=shell('uitest screenCap -p '+device)
 subprocess.run(['hdc','file','recv',device,str(root/name)],capture_output=True,check=True,timeout=60);end=time.monotonic();shell('rm -f '+device)
 return {'file':name,'start':start,'end':end,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest(),'ready':matches(root/name,PAYLOAD['reference'])}
baseline=snapshot('baseline.png');assert not baseline['ready'],'stopped app still matches complete forecast'
log=Path('/home/research/ohm-clean/services/weather/requests.jsonl');offset=log.stat().st_size
record={'status':'FAIL','baseline':baseline,'cache_cleanup':clean,'frames':[]};record['launch_start']=time.monotonic()
try:
 launch=shell('aa start -b '+BUNDLE+' -a AlatusAbility');assert 'start ability successfully' in launch
 record['launch_command_end']=time.monotonic();pid=shell('pidof '+BUNDLE).strip();assert pid.isdigit();record['pid']=pid;record['start_ticks']=shell('cat /proc/'+pid+'/stat').rsplit(')',1)[1].split()[19]
 for index in range(80):
  frame=snapshot(f'frame-{index:03d}.png');record['frames'].append(frame)
  if frame['ready']:break
  if time.monotonic()-record['launch_start']>60:raise ValueError('complete icons did not appear within 60 seconds')
 else:raise ValueError('complete icons not observed')
 record['layout']=ui.layout();assert icon_boxes(record['layout'])==PAYLOAD['reference']['boxes']
 assert shell('pidof '+BUNDLE).strip()==pid and shell('cat /proc/'+pid+'/stat').rsplit(')',1)[1].split()[19]==record['start_ticks']
 record['status']='PIXEL_SCREEN_CAPTURED'
finally:
 record['requests']=[json.loads(x) for x in log.read_bytes()[offset:].decode().splitlines()]
 (root/'capture.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(record['status'])
'''
    print(remote.python(code,{'signed_hap':sign['signed_hap'],'signed_sha256':sign['audit']['sha256'],'reference':reference,'target':target},timeout=300),flush=True)
    remote.download(target+'/capture.json',folder/'capture.json');record=json.loads((folder/'capture.json').read_text())
    if record['status']!='PIXEL_SCREEN_CAPTURED':raise ValueError(record['status'])
    for frame in [record['baseline'],*record['frames']]:
        remote.download(target+'/'+frame['file'],folder/frame['file'])
        if hashlib.sha256((folder/frame['file']).read_bytes()).hexdigest()!=frame['sha256'] or matches(folder/frame['file'],reference)!=frame['ready']:raise ValueError('native frame changed or classification differs')
    after=prepare(remote,base/CASE/'fixed/app-export.hap');same_instance(before,after)
    ready=record['frames'][-1];not_ready=[f for f in record['frames'] if not f['ready']]
    bounds={'lower_s':max(0,(not_ready[-1]['start'] if not_ready else record['launch_start'])-record['launch_start']),'upper_s':ready['end']-record['launch_start']}
    record.update(case=CASE,variant=variant,signed_sha256=sign['audit']['sha256'],reference_sha256=hashlib.sha256((ROOT/'validation/weather-icons-native-reference.json').read_bytes()).hexdigest(),fixture_before=before,fixture_after=after,latency_bounds=bounds,performance_accepted=False)
    (folder/'capture.json').write_text(json.dumps(record,indent=2)+'\n');print(variant,bounds,flush=True);return record

if __name__=='__main__':
    r=Remote('hkrc');u=capture(r,'unfixed');f=capture(r,'fixed');print('CONSERVATIVE SCREEN RATIO',u['latency_bounds']['lower_s']/f['latency_bounds']['upper_s'],flush=True)
