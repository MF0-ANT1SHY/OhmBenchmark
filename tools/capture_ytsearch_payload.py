"""Collect normal typed search payloads with native scheduler diagnostics."""
import hashlib,json
from pathlib import Path
from remote_device import Remote
from ytsearch_service_fixture import prepare
from ytsearch_progress import verify_results,verify_requests
ROOT=Path(__file__).resolve().parents[1]
CASE='ytmusic_search_no_debounce'
BUNDLE='com.example.myapplication'


def capture(remote,variant,number,namespace='search-payload-v2'):
    base=ROOT/'artifacts/candidate-builds/ytsearch-v2';folder=base/namespace/variant/f'round-{number}';folder.mkdir(parents=True,exist_ok=False)
    sign=json.loads((base/CASE/variant/'sign.json').read_text())
    before=prepare(remote)
    (folder/'fixture-before.json').write_text(json.dumps(before,indent=2)+'\n')
    installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
    if 'install bundle successfully' not in installed:raise ValueError(installed)
    target='/home/research/ohm-clean/ytsearch-v2/'+namespace+'/'+variant+'/round-'+str(number)
    for module in ('native_trace_record.py','rss_refresh_progress.py','ui_driver.py'):
        remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
    plan=json.loads((ROOT/'cases'/CASE/'testcase/PerfLoad_ytmusic_0030.workload.json').read_text())
    (folder/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    code=r'''import hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
BUNDLE='com.example.myapplication'
from ui_driver import UI
from native_trace_record import TRACE_ROOT,BUFFER_KB,cpu_set,bracket_cpus
subprocess.run(['hdc','rport','tcp:18493','tcp:18493'],check=True,capture_output=True)
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
def shell(c):
 p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=120);assert p.returncode==0;return p.stdout
root=Path(PAYLOAD['target']).resolve();root.mkdir(parents=True,exist_ok=False);ui=UI(shell,BUNDLE,'EntryAbility')
ui.run([{'op':'stop'},{'op':'launch'}]);ui.run(PAYLOAD['plan']['setup'])
initial_layout=ui.layout()
assert any(n.get('type')=='TextInput' and n.get('text','')=='' for n in UI.nodes(initial_layout))
log=Path('/home/research/ohm-clean/services/ytsearch/requests.jsonl');offset=log.stat().st_size
record={'status':'FAIL','initial_layout':initial_layout}
assert not shell('pidof hiperf').strip() and shell(f'{"cat"} {TRACE_ROOT}/tracing_on').strip()=='0','another profiler is active'
record['online_cpus_before']=cpu_set(shell('cat /sys/devices/system/cpu/online'));original_buffer=shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip();assert original_buffer.isdigit();record['buffer_size_kb_before']=int(original_buffer)
owned=False;acknowledged=False;token=uuid.uuid4().hex;record['marker_token']=token;trace_device='/data/local/tmp/ytsearch-trace-'+token+'.htrace'
try:
 begin=shell(f'hitrace --trace_begin --trace_clock boot -b {BUFFER_KB} sched');record['trace_begin_output']=begin;assert 'OpenRecording done' in begin
 owned=True;acknowledged=True;assert shell(f'cat {TRACE_ROOT}/tracing_on').strip()=='1';record['clock_before']=shell(f'cat {TRACE_ROOT}/trace_clock').strip();assert '[boot]' in record['clock_before']
 bracket_cpus(shell,record['online_cpus_before']);assert not shell(f"echo 'W:{token}:begin' > {TRACE_ROOT}/trace_marker").strip()
 pid=shell('pidof '+BUNDLE).strip();assert pid.isdigit();record['pid']=pid;record['start_ticks']=shell('cat /proc/'+pid+'/stat').rsplit(')',1)[1].split()[19];record['process_before']={'pid':int(pid),'start_ticks':int(record['start_ticks']),'command':shell('cat /proc/'+pid+'/cmdline')};assert record['process_before']['command'].split('\0',1)[0].strip()==BUNDLE
 record['action_start_monotonic']=time.monotonic();ui.run(PAYLOAD['plan']['measured']);ui.run(PAYLOAD['plan']['verify']);ui.run([{'op':'wait','selector':{'text':'Electronic Dawn','match':'exact'},'timeout_s':60}]);record['layout']=ui.layout()
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
    print(remote.python(code,{'signed_hap':sign['signed_hap'],'signed_sha256':sign['audit']['sha256'],'plan':plan,'target':target},timeout=300),flush=True)
    remote.download(target+'/capture.json',folder/'capture.json');record=json.loads((folder/'capture.json').read_text())
    if record['status']!='CAPTURED':raise ValueError(record['status'])
    remote.download(target+'/trace.htrace',folder/'trace.htrace')
    from scheduler_cpu import compute,window_from_markers
    start,end=window_from_markers(folder/'trace.htrace',record['marker_token'],record['pids'])
    record['scheduler_cpu']=compute(folder/'trace.htrace',record['pids'],start,end,record['online_cpus_before'])
    after=prepare(remote)
    if before!=after:raise ValueError('ordinary song service changed')
    record.update(install_output=installed,case=CASE,variant=variant,round=number,measurement_revision=namespace,plan_sha256=hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest(),signed_sha256=sign['audit']['sha256'],fixture_before=before,fixture_after=after,performance_accepted=False)
    (folder/'capture.json').write_text(json.dumps(record,indent=2)+'\n')
    verify_results(record['layout']);record['network_payload']=verify_requests(record)
    (folder/'capture.json').write_text(json.dumps(record,indent=2)+'\n');print(variant,record['network_payload'],flush=True);return record
