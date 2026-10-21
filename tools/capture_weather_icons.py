"""Collect pixel-complete cold launch with independent native scheduling diagnostics."""
import hashlib,json
from pathlib import Path
from remote_device import Remote
from weather_service_fixture import prepare,same_instance
from weather_icon_pixels import matches,icon_boxes
ROOT=Path(__file__).resolve().parents[1]
CASE='weatherassistant_remote_weather_icons'
BUNDLE='com.alatus.futureweather'


def capture(remote,variant,number,namespace='image-ready-v2'):
    base=ROOT/'artifacts/candidate-builds/weather-icons-v2';folder=base/namespace/variant/f'round-{number}';folder.mkdir(parents=True,exist_ok=False)
    reference=json.loads((ROOT/'validation/weather-icons-native-reference.json').read_text());sign=json.loads((base/CASE/variant/'sign.json').read_text())
    before=prepare(remote,base/CASE/'fixed/app-export.hap')
    (folder/'fixture-before.json').write_text(json.dumps(before,indent=2)+'\n')
    installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
    if 'install bundle successfully' not in installed:raise ValueError(installed)
    remote.upload(ROOT/'tools/weather_icon_pixels.py','/home/research/ohm-clean/tools/weather_icon_pixels.py')
    target='/home/research/ohm-clean/weather-icons-v2/'+namespace+'/'+variant+'/round-'+str(number)
    for module in ('native_trace_record.py','rss_refresh_progress.py','ui_driver.py'):
        remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
    plan={'bundle':BUNDLE,'ability':'AlatusAbility','description':'Open the weather forecast','setup':[{'op':'stop'}],'measured':[{'op':'launch'}],'verify':[{'op':'wait','selector':{'text':'深圳市','match':'exact'},'timeout_s':120},{'op':'wait','selector':{'text':'近期天气','match':'exact'},'timeout_s':120}]}
    (folder/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    code=r'''import hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/venvs/image/Lib/site-packages').resolve()))
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
from weather_icon_pixels import matches,icon_boxes,BUNDLE
from ui_driver import UI
from native_trace_record import TRACE_ROOT,BUFFER_KB,cpu_set,bracket_cpus
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
record={'status':'FAIL','baseline':baseline,'cache_cleanup':clean,'frames':[]}
assert not shell('pidof hiperf').strip() and shell(f'{"cat"} {TRACE_ROOT}/tracing_on').strip()=='0','another profiler is active'
record['online_cpus_before']=cpu_set(shell('cat /sys/devices/system/cpu/online'));original_buffer=shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip();assert original_buffer.isdigit();record['buffer_size_kb_before']=int(original_buffer)
owned=False;acknowledged=False;token=uuid.uuid4().hex;record['marker_token']=token;trace_device='/data/local/tmp/weather-trace-'+token+'.htrace'
try:
 begin=shell(f'hitrace --trace_begin --trace_clock boot -b {BUFFER_KB} sched');record['trace_begin_output']=begin;assert 'OpenRecording done' in begin
 owned=True;acknowledged=True;assert shell(f'cat {TRACE_ROOT}/tracing_on').strip()=='1';record['clock_before']=shell(f'cat {TRACE_ROOT}/trace_clock').strip();assert '[boot]' in record['clock_before']
 bracket_cpus(shell,record['online_cpus_before']);assert not shell(f"echo 'W:{token}:begin' > {TRACE_ROOT}/trace_marker").strip()
 record['launch_start']=time.monotonic();record['action_start_monotonic']=record['launch_start']
 launch=shell('aa start -b '+BUNDLE+' -a AlatusAbility');assert 'start ability successfully' in launch
 record['launch_command_end']=time.monotonic();pid=shell('pidof '+BUNDLE).strip();assert pid.isdigit();record['pid']=pid;record['start_ticks']=shell('cat /proc/'+pid+'/stat').rsplit(')',1)[1].split()[19];record['process_before']={'pid':int(pid),'start_ticks':int(record['start_ticks']),'command':shell('cat /proc/'+pid+'/cmdline')};assert record['process_before']['command'].split('\0',1)[0].strip()==BUNDLE
 for index in range(80):
  frame=snapshot(f'frame-{index:03d}.png');record['frames'].append(frame)
  if frame['ready']:break
  if time.monotonic()-record['launch_start']>60:raise ValueError('complete icons did not appear within 60 seconds')
 else:raise ValueError('complete icons not observed')
 record['layout']=ui.layout();assert icon_boxes(record['layout'])==PAYLOAD['reference']['boxes']
 assert shell('pidof '+BUNDLE).strip()==pid and shell('cat /proc/'+pid+'/stat').rsplit(')',1)[1].split()[19]==record['start_ticks']
 record['action_end_monotonic']=time.monotonic();assert not shell(f"echo 'W:{token}:end' > {TRACE_ROOT}/trace_marker").strip();bracket_cpus(shell,record['online_cpus_before'])
 record['process_after']={'pid':int(pid),'start_ticks':int(shell('cat /proc/'+pid+'/stat').rsplit(')',1)[1].split()[19]),'command':shell('cat /proc/'+pid+'/cmdline')};assert record['process_after']==record['process_before']
 record['online_cpus_after']=cpu_set(shell('cat /sys/devices/system/cpu/online'));record['clock_after']=shell(f'cat {TRACE_ROOT}/trace_clock').strip();assert record['online_cpus_after']==record['online_cpus_before'] and record['clock_after']==record['clock_before']
 record['saved_tgids']=shell(f'cat {TRACE_ROOT}/saved_tgids');record['trace_finish_output']=shell('hitrace --trace_finish -o '+trace_device);assert shell(f'cat {TRACE_ROOT}/tracing_on').strip()=='0';owned=False
 subprocess.run(['hdc','file','recv',trace_device,str(root/'trace.htrace')],check=True,capture_output=True,timeout=180);record['pids']=[int(pid)];record['status']='CAPTURED'
finally:
 if owned:shell('hitrace --trace_finish_nodump')
 if acknowledged:
  assert shell(f'cat {TRACE_ROOT}/tracing_on').strip()=='0'
  if shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip()!=original_buffer:shell(f'echo {original_buffer} > {TRACE_ROOT}/buffer_size_kb')
  record['buffer_size_kb_after']=int(shell(f'cat {TRACE_ROOT}/buffer_size_kb'));assert record['buffer_size_kb_after']==record['buffer_size_kb_before']
 record['requests']=[json.loads(x) for x in log.read_bytes()[offset:].decode().splitlines()]
 (root/'capture.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(record['status'])
'''
    print(remote.python(code,{'signed_hap':sign['signed_hap'],'signed_sha256':sign['audit']['sha256'],'reference':reference,'target':target},timeout=300),flush=True)
    remote.download(target+'/capture.json',folder/'capture.json');record=json.loads((folder/'capture.json').read_text())
    if record['status']!='CAPTURED':raise ValueError(record['status'])
    for frame in [record['baseline'],*record['frames']]:
        remote.download(target+'/'+frame['file'],folder/frame['file'])
        if hashlib.sha256((folder/frame['file']).read_bytes()).hexdigest()!=frame['sha256'] or matches(folder/frame['file'],reference)!=frame['ready']:raise ValueError('native frame changed or classification differs')
    remote.download(target+'/trace.htrace',folder/'trace.htrace')
    from scheduler_cpu import compute,window_from_markers
    start,end=window_from_markers(folder/'trace.htrace',record['marker_token'],record['pids'])
    record['scheduler_cpu']=compute(folder/'trace.htrace',record['pids'],start,end,record['online_cpus_before'])
    after=prepare(remote,base/CASE/'fixed/app-export.hap');same_instance(before,after)
    ready=record['frames'][-1];not_ready=[f for f in record['frames'] if not f['ready']]
    bounds={'lower_s':max(0,(not_ready[-1]['start'] if not_ready else record['launch_start'])-record['launch_start']),'upper_s':ready['end']-record['launch_start']}
    record.update(case=CASE,variant=variant,round=number,measurement_revision=namespace,plan_sha256=hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest(),signed_sha256=sign['audit']['sha256'],reference_sha256=hashlib.sha256((ROOT/'validation/weather-icons-native-reference.json').read_bytes()).hexdigest(),fixture_before=before,fixture_after=after,latency_bounds=bounds,performance_accepted=False)
    (folder/'capture.json').write_text(json.dumps(record,indent=2)+'\n');print(variant,bounds,flush=True);return record

