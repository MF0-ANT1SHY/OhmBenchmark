"""Capture warmed ordinary city refreshes and bracketed kernel PSS windows."""
import hashlib,json
from pathlib import Path
from weather_session_service_fixture import prepare
from weather_session_memory import growth_bounds,verify_capture
ROOT=Path(__file__).resolve().parents[1]
CASE='weatherassistant_http_session_leak'

def capture(remote,variant,number,revision='growth-v5'):
    if revision not in ('growth-v4','growth-v5'):raise ValueError('unknown prospective growth contract')
    count=15 if revision=='growth-v4' else 60
    base=ROOT/'artifacts/candidate-builds/weather-sessions-v3';folder=base/revision/variant/f'round-{number}';folder.mkdir(parents=True,exist_ok=False)
    contract_path=ROOT/('validation/weather-sessions-'+revision+'-contract.json')
    contract=json.loads(contract_path.read_text())
    if contract['measurement_revision']!=revision or contract['measured_returns']!=count or contract['required_successful_forecasts_per_trial']!=10*count:raise ValueError('prospective refresh contract differs')
    contract_hash=hashlib.sha256(contract_path.read_bytes()).hexdigest()
    before=prepare(remote);(folder/'fixture-before.json').write_text(json.dumps(before,indent=2)+'\n')
    sign=json.loads((base/CASE/variant/'sign.json').read_text());installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
    if 'install bundle successfully' not in installed:raise ValueError(installed)
    for module in ('ui_driver.py','system_pss.py'):remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
    original=json.loads((ROOT/'cases'/CASE/'testcase/MemLoad_weatherassistant_0010.workload.json').read_text());checks=original['setup'];actions=original['measured'][0]['actions']+checks
    plan={'bundle':original['bundle'],'ability':original['ability'],'description':'Refresh the saved city forecasts','setup':checks+[{'op':'repeat','count':10,'actions':actions},{'op':'pause','seconds':3}],'measured':[{'op':'repeat','count':count,'actions':actions}],'verify':checks}
    (folder/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    target='/home/research/ohm-clean/weather-sessions-v3/'+revision+'/'+variant+'/round-'+str(number)
    code="import hashlib,json,subprocess,sys,time\nfrom pathlib import Path\nsys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))\nfrom ui_driver import UI\nfrom system_pss import read_process,verify_window\nsubprocess.run(['hdc','rport','tcp:18494','tcp:18494'],check=True,capture_output=True)\ndef shell(c):\n p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=120);assert p.returncode==0;return p.stdout\nfor name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):assert not shell('pidof '+name).strip()\nassert shell('cat /sys/kernel/tracing/tracing_on').strip()=='0'\nclass Reader:\n def hdc(self,args):\n  assert args[0]=='shell' and len(args)==2;return shell(args[1])\nreader=Reader();bundle='com.alatus.futureweather';ui=UI(shell,bundle,'AlatusAbility');root=Path(PAYLOAD['target']).resolve();root.mkdir(parents=True,exist_ok=False)\nassert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']\nshell('aa force-stop cn.seayj.sepweather')\nui.run([{'op':'stop'},{'op':'launch'}]);ui.run(PAYLOAD['plan']['setup'])\npid=int(shell('pidof '+bundle).strip());result={'status':'RUNNING','snapshots':[],'steps':[],'warmup_count':10,'initial_layout':ui.layout(),'pids':[pid]}\ndef snapshot(phase):\n start=time.monotonic();row=read_process(reader,pid,bundle);row.update(phase=phase,monotonic=time.monotonic(),read_start_monotonic=start);result['snapshots'].append(row);return row\nresult['baseline_samples']=[snapshot('before') for _ in range(3)];result['snapshots']=[result['baseline_samples'][-1]]\nlog=Path('/home/research/ohm-clean/services/weather_session/requests.jsonl');offset=log.stat().st_size;result['action_start_monotonic']=time.monotonic()\ntry:\n for index in range(PAYLOAD['plan']['measured'][0]['count']):\n  ui.run(PAYLOAD['plan']['measured'][0]['actions']);result['steps'].append({'number':index+1,'layout':ui.layout()});snapshot('workload');(root/'progress.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')\n time.sleep(5);result['action_end_monotonic']=time.monotonic();result['post_samples']=[snapshot('after') for _ in range(3)];result['snapshots']=result['snapshots'][:-3]+[result['post_samples'][-1]];result['app_pss_bytes']=result['snapshots'][-1]['pss_bytes'];verify_window(result,bundle);result['status']='CAPTURED'\nfinally:\n result['requests']=[json.loads(x) for x in log.read_bytes()[offset:].decode().splitlines()];(root/'capture.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')\nprint(json.dumps({'status':result['status'],'pss':[s['pss_bytes'] for s in result['snapshots']],'requests':len(result['requests'])}))\n"
    print(remote.python(code,{'target':target,'plan':plan,'signed_hap':sign['signed_hap'],'signed_sha256':sign['audit']['sha256']},timeout=1800),flush=True)
    remote.download(target+'/capture.json',folder/'capture.json');record=json.loads((folder/'capture.json').read_text())
    after=prepare(remote)
    if before!=after:raise ValueError('ordinary ten-city service changed')
    record.update(case=CASE,variant=variant,round=number,contract_sha256=contract_hash,measurement_revision=revision,metric='app_pss_growth_bytes',signed_sha256=sign['audit']['sha256'],install_output=installed,fixture_before=before,fixture_after=after,plan_sha256=hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest(),performance_accepted=False)
    record['growth_bounds']=growth_bounds([s['pss_bytes'] for s in record['baseline_samples']],[s['pss_bytes'] for s in record['post_samples']])
    (folder/'capture.json').write_text(json.dumps(record,indent=2)+'\n');verify_capture(record,folder);print(variant,record['growth_bounds'],flush=True);return record
