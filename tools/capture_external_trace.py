#!/usr/bin/env python3
"""Capture ordinary refresh CPU time with native scheduling, never app probes."""
import argparse
import hashlib
import json
from pathlib import Path

from reader_data_fixture import prepare, finish
from remote_device import Remote
from scheduler_cpu import compute, window_from_markers

ROOT = Path(__file__).resolve().parents[1]
CASE = 'sheafreader_refresh_feeds_sequential'


def capture(remote, case, variant, round_number, fixture):
    if case['id'] != CASE or case['test_oracle']['metric'] != 'trace_cpu_ms':
        raise ValueError('native refresh trace provided to an unsupported case or metric')
    if variant not in ('unfixed', 'fixed') or round_number not in (1, 2, 3):
        raise ValueError('paired native captures require variants and rounds 1 to 3')
    if (remote.hdc(['shell', 'pidof hiperf']).strip()
            or remote.hdc(['shell', 'cat /sys/kernel/tracing/tracing_on']).strip() != '0'):
        raise ValueError('another profiler is active; no installs or UI actions performed')
    folder = ROOT/'artifacts/clean'/CASE/variant
    sign = json.loads((folder/'sign.json').read_text())
    plan = ROOT/'cases'/CASE/case['testcase']['workload']
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    output = folder/'trace-captures'/f'round-{round_number}'
    output.mkdir(parents=True, exist_ok=False)
    base = f'/home/research/ohm-clean/{CASE}/{variant}/trace-captures/round-{round_number}'
    bundles = sorted({json.loads(p.read_text())['host_app']['bundle_name']
                      for p in (ROOT/'cases').glob('*/case.json')})
    for bundle in bundles:
        remote.hdc(['shell', 'aa force-stop '+bundle])
    installed = remote.hdc(['install', '-r', sign['signed_hap']], timeout=180)
    if 'install bundle successfully' not in installed:
        raise RuntimeError(installed)
    before = prepare(remote, case, fixture)
    remote.upload(plan, base+'/plan.json')
    for name in ('ui_driver.py', 'native_trace_record.py', 'rss_refresh_progress.py'):
        remote.upload(ROOT/'tools'/name, '/home/research/ohm-clean/tools/'+name)
    code = """import hashlib,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools')
from ui_driver import UI
from native_trace_record import record
def shell(command):
 p=subprocess.run(['hdc','shell',command],capture_output=True,text=True,timeout=180)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout+p.stderr
root=Path(PAYLOAD['root']);root.mkdir(parents=True,exist_ok=True)
plan_path=root/'plan.json'
assert hashlib.sha256(plan_path.read_bytes()).hexdigest()==PAYLOAD['plan_sha256']
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
plan=json.loads(plan_path.read_text())
record(UI(shell,plan['bundle'],plan['ability']),plan,root)
"""
    remote.python(code, {'root': base, 'plan_sha256': digest, 'signed_hap': sign['signed_hap'],
                         'signed_sha256': sign['audit']['sha256']}, timeout=900)
    remote.download(base+'/capture.json', output/'capture.json')
    receipt = json.loads((output/'capture.json').read_text())
    receipt.update({'case': CASE, 'variant': variant, 'round': round_number,
                    'plan_sha256': digest, 'signed_sha256': sign['audit']['sha256'],
                    'fixture_sha256': before['sha256'], 'reader_fixture_before': before,
                    'remote_artifacts': base, 'performance_verified': False})
    (output/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    if receipt['status'] != 'CAPTURED':
        raise RuntimeError(receipt.get('error', 'native trace was not captured'))
    receipt['reader_fixture_after'] = finish(remote, case, before)
    (output/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    remote.download(base+'/trace.htrace', output/'trace.htrace')
    started, ended = window_from_markers(output/'trace.htrace', receipt['marker_token'], receipt['pids'])
    receipt['scheduler_cpu'] = compute(output/'trace.htrace', receipt['pids'], started, ended,
                                       receipt['online_cpus_before'])
    (output/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(f'{CASE}/{variant}/round-{round_number}: native CPU {receipt["scheduler_cpu"]["app_cpu_ms"]:.3f} ms')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=[CASE])
    parser.add_argument('variant', choices=['unfixed', 'fixed'])
    parser.add_argument('--round', type=int, required=True, choices=[1, 2, 3])
    parser.add_argument('--reader-fixture', type=Path, required=True)
    parser.add_argument('--remote', default='cityuPC')
    args = parser.parse_args()
    case = json.loads((ROOT/'cases'/args.case/'case.json').read_text())
    capture(Remote(args.remote), case, args.variant, args.round, args.reader_fixture)


if __name__ == '__main__':
    main()
