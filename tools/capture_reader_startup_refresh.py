#!/usr/bin/env python3
"""Collect a fresh startup-refresh pair member without instrumenting the app."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid

from reader_data_fixture import prepare, finish, verify_preparation
from remote_device import Remote
from scheduler_cpu import compute, window_from_markers

ROOT = Path(__file__).resolve().parents[1]
CASE = 'sheafreader_refresh_feeds_sequential'
REVISION = 'startup-refresh-latency-v7'


def capture(remote, variant, number):
    case = json.loads((ROOT/'cases'/CASE/'case.json').read_text())
    base = ROOT/'artifacts/candidate-builds/reader-refresh-v3'
    package = base/CASE/variant
    sign = json.loads((package/'sign.json').read_text())
    if hashlib.sha256((package/'app-export.hap').read_bytes()).hexdigest() != sign['audit']['sha256']:
        raise ValueError('candidate signature bytes changed')
    if remote.hdc(['shell', 'cat /sys/kernel/tracing/tracing_on']).strip() != '0' or remote.hdc(['shell', 'pidof hiperf']).strip():
        raise ValueError('another native profiler is active')
    output = base/REVISION/variant/f'round-{number}'
    output.mkdir(parents=True, exist_ok=False)
    installed = remote.hdc(['install', '-r', sign['signed_hap']], timeout=180)
    if 'install bundle successfully' not in installed:
        raise ValueError(installed)
    before = prepare(remote, case, ROOT/'artifacts/fixtures/rss-short-journals/reader-10-short.db')
    if before['service'].get('network_delay_s') != 1.5:
        raise ValueError('declared RSS delay differs from current service')
    (output/'preparation.json').write_text(json.dumps(before, indent=2)+'\n')
    plan = {'bundle': 'com.sheafreader.hm', 'ability': 'EntryAbility',
            'description': 'Open the reader and wait for its automatic subscription refresh',
            'setup': [{'op': 'stop'}],
            'measured': [{'op': 'launch'}, {'op': 'pause', 'seconds': 1},
                         {'op': 'wait', 'selector': {'type': 'Button', 'bounds': '[195,326][296,427]', 'enabled': 'true', 'match': 'exact'}, 'timeout_s': 90}],
            'verify': [{'op': 'wait', 'selector': {'text': 'Journal 1 article 1', 'match': 'exact'}, 'timeout_s': 60}]}
    (output/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    modules = ('ui_driver.py', 'native_trace_record.py', 'native_startup_refresh_record.py',
               'reader_refresh_latency.py', 'rss_refresh_progress.py')
    for name in modules:
        remote.upload(ROOT/'tools'/name, '/home/research/ohm-clean/tools/'+name)
    remote_base = f'/home/research/ohm-clean/reader-refresh-v3/{REVISION}/{variant}/round-{number}-{uuid.uuid4().hex}'
    code = '''import hashlib,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
from ui_driver import UI
from native_startup_refresh_record import record
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
p=subprocess.run(['hdc','rport','tcp:18491','tcp:18491'],capture_output=True,text=True,check=True)
assert 'OK' in p.stdout,p.stdout+p.stderr
ports=subprocess.run(['hdc','fport','ls'],capture_output=True,text=True,check=True).stdout
assert '18491' in ports,ports
def shell(command):
 p=subprocess.run(['hdc','shell',command],capture_output=True,text=True,timeout=180)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
r=record(UI(shell,PAYLOAD['plan']['bundle']),PAYLOAD['plan'],Path(PAYLOAD['root']))
print(json.dumps({'status':r['status'],'error':r.get('error'),'latency':r.get('latency_bounds')}))
'''
    print(remote.python(code, {'signed_hap': sign['signed_hap'], 'signed_sha256': sign['audit']['sha256'],
                              'root': remote_base, 'plan': plan}, timeout=900), flush=True)
    remote.download(remote_base+'/capture.json', output/'capture.json')
    receipt = json.loads((output/'capture.json').read_text())
    receipt.update(case=CASE, variant=variant, round=number, measurement_revision=REVISION,
                   signed_sha256=sign['audit']['sha256'], remote_artifacts=remote_base,
                   fixture_sha256=before['sha256'], reader_fixture_before=before,
                   plan_sha256=hashlib.sha256((output/'plan.json').read_bytes()).hexdigest(),
                   collector_sources={name: hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in modules})
    (output/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    if receipt['status'] != 'CAPTURED':
        raise ValueError(receipt.get('error', 'native collection failed'))
    after = finish(remote, case, before)
    verify_preparation(before, after)
    receipt['reader_fixture_after'] = after
    remote.download(remote_base+'/trace.htrace', output/'trace.htrace')
    start, end = window_from_markers(output/'trace.htrace', receipt['marker_token'], receipt['pids'])
    receipt['scheduler_cpu'] = compute(output/'trace.htrace', receipt['pids'], start, end, receipt['online_cpus_before'])
    (output/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(f'{variant}/round-{number}: complete native capture {receipt["latency_bounds"]}', flush=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variant', choices=('unfixed', 'fixed'))
    parser.add_argument('--round', type=int, required=True, choices=(1, 2, 3))
    parser.add_argument('--remote', default='hkrc')
    args = parser.parse_args()
    capture(Remote(args.remote), args.variant, args.round)
