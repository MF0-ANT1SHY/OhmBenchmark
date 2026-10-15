#!/usr/bin/env python3
"""Recover a completed Browser trial after transport timeout; never rerun UI."""
import argparse
import hashlib
import json
from pathlib import Path

from browser_visit_progress import CASE, verify_capture
from remote_device import Remote
from system_pss import start_ticks

ROOT = Path(__file__).resolve().parents[1]


def recover(remote, variant, round_number, fixture):
    case_path = ROOT/'cases'/CASE/'case.json'
    case = json.loads(case_path.read_text())
    base = ROOT/'artifacts/clean'/CASE/variant
    folder = base/'cpu-captures'/f'round-{round_number}'
    if (folder/'capture.json').exists():
        raise ValueError('will not replace an already finalized local capture')
    owner = json.loads((folder/'transport-owner.json').read_text())
    pid = owner['remote_python_pid']
    ticks = start_ticks(owner['remote_python_stat'], pid)
    remote_root = f'/home/research/ohm-clean/{CASE}/{variant}/cpu-captures/round-{round_number}'
    sign = json.loads((base/'sign.json').read_text())
    plan_hash = hashlib.sha256((case_path.parent/case['testcase']['workload']).read_bytes()).hexdigest()
    fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
    workload = json.loads((base/'workload.json').read_text())
    if (workload['status'] != 'PASS' or workload['plan_sha256'] != plan_hash or
            workload['signed_sha256'] != sign['audit']['sha256'] or
            workload['fixture']['sha256'] != fixture_hash):
        raise ValueError('matching validated ordinary input and signed workload required')
    # Poll this exact owner. An elapsed observation budget does not terminate
    # the remote Python job; never launch a replacement while it is live.
    code = """import json,hashlib
from pathlib import Path
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1048576),b''):h.update(block)
 return h.hexdigest()
p=Path('/proc')/str(PAYLOAD['pid']);stat=(p/'stat').read_text() if p.exists() else None
if stat and stat.rsplit(')',1)[1].split()[19]==str(PAYLOAD['ticks']):
 raise RuntimeError('original remote capture job is still live; continue observing the same owner')
root=Path(PAYLOAD['root'])
assert digest(root/'plan.json')==PAYLOAD['plan']
assert digest(Path(PAYLOAD['signed_hap']))==PAYLOAD['signed_sha256']
record=json.loads((root/'capture.json').read_text())
assert record['status']=='CAPTURED','remote trial is incomplete or failed'
print(json.dumps({name:digest(root/name) for name in ('capture.json','report.json','perf.data')}))
"""
    hashes = json.loads(remote.python(code, dict(pid=pid,ticks=ticks,root=remote_root,plan=plan_hash,
                        signed_hap=sign['signed_hap'],signed_sha256=sign['audit']['sha256']),timeout=120))
    for name, local_name in (('capture.json','raw-device-capture.json'),('report.json','report.json')):
        path = folder/local_name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise ValueError('existing local artifact differs; preserve/archive it before any recovery')
        if not path.exists():
            remote.download(remote_root+'/'+name,path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise ValueError('recovered native artifact hash mismatch')
    receipt = json.loads((folder/'raw-device-capture.json').read_text())
    if receipt.get('status') != 'CAPTURED' or receipt.get('event') != 'hw-instructions':
        raise ValueError('native capture did not complete the required instruction event')
    verify_capture(receipt['browser_visits'],receipt['action_start_monotonic'],receipt['action_end_monotonic'])
    if (receipt['pids'] != [owner['app']['pid']] or
            owner['app']['cmdline'].split('\0',1)[0].strip() != case['host_app']['bundle_name']):
        raise ValueError('recovered trial differs from the observed app process')
    start_ticks(owner['app']['stat'],owner['app']['pid'])
    report = json.loads((folder/'report.json').read_text())
    events = [event for event in report['recordSampleInfo'] if event['eventConfigName']=='hw-instructions']
    if len(events) != 1:raise ValueError('ambiguous native instruction event')
    processes = [process for process in events[0]['processes'] if process['pid'] in receipt['pids']]
    if (len(processes) != len(receipt['pids']) or
            any(report['processNameMap'].get(str(p['pid'])) != case['host_app']['bundle_name'] for p in processes)):
        raise ValueError('native samples do not belong to the observed app')
    instructions = sum(p['eventCount'] for p in processes)
    samples = sum(t['sampleCount'] for p in processes for t in p['threads'])
    if instructions <= 0 or samples <= 0:raise ValueError('no app-attributed native samples')
    receipt.update(case=CASE,variant=variant,round=round_number,plan_sha256=plan_hash,
                   signed_sha256=sign['audit']['sha256'],remote_artifacts=remote_root,
                   performance_verified=False,fixture_sha256=fixture_hash,
                   app_instruction_period_sum=instructions,app_samples=samples,
                   transport_recovery={'original_remote_python_pid':pid,'original_remote_start_ticks':ticks,
                                       'native_artifact_sha256':hashes,'ui_rerun':False})
    (folder/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(f'{CASE}/{variant}/round-{round_number}: recovered original CAPTURED trial; no UI rerun',flush=True)
    return receipt


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',required=True,choices=['unfixed','fixed'])
    parser.add_argument('--round',type=int,default=1)
    parser.add_argument('--fixture',required=True,type=Path)
    args=parser.parse_args()
    recover(Remote(),args.variant,args.round,args.fixture)
