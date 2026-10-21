"""Capture the frozen forty-refresh GC-request-conditioned protocol externally."""
import hashlib, json, re
from pathlib import Path
from system_pss import verify_window
from weather_session_memory import growth_bounds
from weather_hourly_memory import verify_requests, verify_capture, frozen_contract
from weather_hourly_service_fixture import prepare
from weather_icon_pixels import icon_boxes
ROOT = Path(__file__).resolve().parents[1]
CASE = 'weatherassistant_http_session_leak'

def capture(remote, variant, number=1, build_root=None, output_root=None):
    count = 40
    revision = 'gc-growth-v7'
    contract_hash = frozen_contract()
    if type(number) is not int or not 1 <= number <= 3 or variant not in ('unfixed', 'fixed') or type(count) is not int or (not 1 <= count <= 120) or (not re.fullmatch('[a-z0-9_-]+', revision)):
        raise ValueError('invalid formal hourly capture request')
    base = Path(build_root).resolve() if build_root is not None else ROOT / 'artifacts/candidate-builds/weather-hourly-v5'
    destination = Path(output_root).resolve() if output_root is not None else base / revision
    folder = destination / variant / f'round-{number}'
    folder.mkdir(parents=True, exist_ok=False)
    before = prepare(remote)
    (folder / 'fixture-before.json').write_text(json.dumps(before, indent=2) + '\n')
    sign = json.loads((base / CASE / variant / 'sign.json').read_text())
    installed = remote.hdc(['install', '-r', sign['signed_hap']], timeout=180)
    if 'install bundle successfully' not in installed:
        raise ValueError(installed)
    for name in ('ui_driver.py', 'system_pss.py'):
        remote.upload(ROOT / 'tools' / name, '/home/research/ohm-clean/tools/' + name)
    case = json.loads((ROOT / 'cases' / CASE / 'case.json').read_text())
    recipe = case.get('acceptance_revision', {}).get('original_workload')
    recipe_path = ROOT / recipe if recipe else ROOT / 'cases' / CASE / 'testcase/MemLoad_weatherassistant_0010.workload.json'
    original = json.loads(recipe_path.read_text())
    checks = original['setup']
    actions = original['measured'][0]['actions'] + checks
    plan = {'bundle': original['bundle'], 'ability': original['ability'], 'description': 'Refresh the saved city forecasts', 'setup': checks + [{'op': 'repeat', 'count': 10, 'actions': actions}, {'op': 'pause', 'seconds': 3}], 'measured': [{'op': 'repeat', 'count': count, 'actions': actions}], 'verify': checks}
    (folder / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    remote_series = revision if output_root is None else revision + '/recapture-' + hashlib.sha256(str(destination).encode()).hexdigest()[:16]
    target = '/home/research/ohm-clean/weather-hourly-v5/' + remote_series + '/' + variant + '/round-' + str(number)
    code = 'import hashlib,json,re,subprocess,sys,time\nfrom pathlib import Path\nsys.path.insert(0,str(Path(\'/home/research/ohm-clean/tools\').resolve()))\nfrom ui_driver import UI\nfrom system_pss import read_process,verify_window\nsubprocess.run([\'hdc\',\'rport\',\'tcp:18496\',\'tcp:18496\'],check=True,capture_output=True)\ndef shell(c):\n p=subprocess.run([\'hdc\',\'shell\',c],capture_output=True,text=True,timeout=120);assert p.returncode==0;return p.stdout\nfor name in (\'hiperf\',\'hiprofiler_cmd\',\'hiprofilerd\',\'native_daemon\'):assert not shell(\'pidof \'+name).strip()\nassert shell(\'cat /sys/kernel/tracing/tracing_on\').strip()==\'0\'\nclass Reader:\n def hdc(self,args):\n  assert args[0]==\'shell\' and len(args)==2;return shell(args[1])\nreader=Reader();bundle=\'com.alatus.futureweather\';ui=UI(shell,bundle,\'AlatusAbility\');root=Path(PAYLOAD[\'target\']).resolve();root.mkdir(parents=True,exist_ok=False)\nassert hashlib.sha256(Path(PAYLOAD[\'signed_hap\']).read_bytes()).hexdigest()==PAYLOAD[\'signed_sha256\']\nshell(\'aa force-stop cn.seayj.sepweather\')\nui.run([{\'op\':\'stop\'},{\'op\':\'launch\'}]);ui.run(PAYLOAD[\'plan\'][\'setup\'])\npid=int(shell(\'pidof \'+bundle).strip());result={\'contract_sha256\':PAYLOAD[\'contract_sha256\'],\'status\':\'RUNNING\',\'snapshots\':[],\'steps\':[],\'warmup_count\':10,\'gc_requests\':[],\'initial_layout\':ui.layout(),\'pids\':[pid]}\ndef snapshot(phase):\n start=time.monotonic();row=read_process(reader,pid,bundle);row.update(phase=phase,monotonic=time.monotonic(),read_start_monotonic=start);result[\'snapshots\'].append(row);return row\ndef gc_request(phase):\n start=time.monotonic();command=\'hidumper --mem-jsheap \'+str(pid)+\' --gc\'\n wrapped=command+"; task_gc_rc=$?; printf \'\\\\n__WEATHER_GC_EXIT__=%s\\\\n\' \\"$task_gc_rc\\""\n output=shell(wrapped);match=re.search(r\'__WEATHER_GC_EXIT__=(\\d+)\\s*$\',output);assert match and int(match.group(1))==0,output\n row={\'phase\':phase,\'pid\':pid,\'command\':command,\'native_exit_code\':int(match.group(1)),\'raw_output\':output,\'start_monotonic\':start,\'end_monotonic\':time.monotonic(),\'settle_seconds\':10}\n time.sleep(10);row[\'settle_end_monotonic\']=time.monotonic();result[\'gc_requests\'].append(row)\ngc_request(\'before\')\nresult[\'baseline_samples\']=[snapshot(\'before\') for _ in range(3)];result[\'snapshots\']=[result[\'baseline_samples\'][-1]]\nlog=Path(\'/home/research/ohm-clean/services/weather_hourly/requests.jsonl\');offset=log.stat().st_size;result[\'action_start_monotonic\']=time.monotonic()\ntry:\n for index in range(PAYLOAD[\'plan\'][\'measured\'][0][\'count\']):\n  ui.run(PAYLOAD[\'plan\'][\'measured\'][0][\'actions\']);result[\'steps\'].append({\'number\':index+1,\'layout\':ui.layout()});snapshot(\'workload\');(root/\'progress.json\').write_text(json.dumps(result,ensure_ascii=False),encoding=\'utf8\')\n time.sleep(5);result[\'action_end_monotonic\']=time.monotonic();gc_request(\'after\');result[\'post_samples\']=[snapshot(\'after\') for _ in range(3)];result[\'snapshots\']=result[\'snapshots\'][:-3]+[result[\'post_samples\'][-1]];result[\'app_pss_bytes\']=result[\'snapshots\'][-1][\'pss_bytes\'];verify_window(result,bundle);result[\'final_layout\']=ui.layout();result[\'status\']=\'CAPTURED\'\nfinally:\n result[\'requests\']=[json.loads(x) for x in log.read_bytes()[offset:].decode().splitlines()];(root/\'capture.json\').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding=\'utf8\')\nprint(json.dumps({\'status\':result[\'status\'],\'pss\':[s[\'pss_bytes\'] for s in result[\'snapshots\']],\'requests\':len(result[\'requests\'])}))\n'
    print(remote.python(code, {'target': target, 'plan': plan, 'signed_hap': sign['signed_hap'], 'signed_sha256': sign['audit']['sha256'], 'contract_sha256': contract_hash}, timeout=2400), flush=True)
    remote.download(target + '/capture.json', folder / 'capture.json')
    record = json.loads((folder / 'capture.json').read_text())
    after = prepare(remote)
    if before != after:
        raise ValueError('ordinary forecast service changed')
    record.update(case=CASE, variant=variant, round=number, measurement_revision=revision, metric='app_gc_requested_pss_growth_bytes', measured_returns=count, signed_sha256=sign['audit']['sha256'], install_output=installed, fixture_before=before, fixture_after=after, plan_sha256=hashlib.sha256((folder / 'plan.json').read_bytes()).hexdigest(), performance_accepted=False, gc_completion_claimed=False)
    record['growth_bounds'] = growth_bounds([s['pss_bytes'] for s in record['baseline_samples']], [s['pss_bytes'] for s in record['post_samples']])
    (folder / 'capture.json').write_text(json.dumps(record, indent=2) + '\n')
    from weather_session_gc_memory import verify_gc_receipts
    verify_gc_receipts(record)
    verify_window(record, 'com.alatus.futureweather')
    verify_requests(record, count)
    icon_boxes(record['initial_layout'])
    icon_boxes(record['final_layout'])
    for step in record['steps']:
        icon_boxes(step['layout'])
    assert len(record['steps']) == count and len(record['gc_requests']) == 2
    if frozen_contract() != contract_hash:
        raise ValueError('frozen contract changed during capture')
    verify_capture(record, folder)
    print(variant, record['growth_bounds'], flush=True)
    return record

if __name__ == '__main__':
    import argparse
    from remote_device import Remote
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='hkrc')
    parser.add_argument('--variant', required=True, choices=('unfixed', 'fixed'))
    parser.add_argument('--round', dest='round_number', type=int, required=True, choices=(1, 2, 3))
    parser.add_argument('--build-root', type=Path, help='Root containing case/variant signed build receipts; defaults to the frozen candidate build directory')
    parser.add_argument('--output-root', type=Path, help='New local root for variant/round-N native evidence; existing trial directories are refused')
    args = parser.parse_args()
    capture(Remote(args.host), args.variant, args.round_number, args.build_root, args.output_root)
