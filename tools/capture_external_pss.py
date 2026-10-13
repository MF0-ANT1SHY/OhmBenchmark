#!/usr/bin/env python3
"""Collect kernel process PSS during a validated, normal external UI workload.

This records evidence, not a performance verdict. Fixture preparation remains
outside the app and must precede this command; no memory probes are injected.
"""
import argparse
import hashlib
import json
from pathlib import Path

from remote_device import Remote
from system_pss import capture_window
from install_search_history_fixture import install as install_search_history

ROOT=Path(__file__).resolve().parents[1]


def capture(remote,case,variant,round_number,search_history_fixture=None,preferences_path=None):
    if case['test_oracle']['metric']!='app_pss_bytes':
        raise ValueError('PSS collector cannot validate a different metric')
    cid=case['id']
    bundle=case['host_app']['bundle_name']
    folder=ROOT/'artifacts/clean'/cid/variant
    if round_number<1:
        raise ValueError('round number must be positive')
    output=folder/'pss-captures'/f'round-{round_number}'
    if output.exists():
        raise FileExistsError('refusing to replace an existing raw PSS trial')
    sign=json.loads((folder/'sign.json').read_text())
    plan=ROOT/'cases'/cid/case['testcase']['workload']
    plan_hash=hashlib.sha256(plan.read_bytes()).hexdigest()
    validated=json.loads((folder/'workload.json').read_text())
    if (sign['status']!='PASS' or validated['status']!='PASS'
            or validated['plan_sha256']!=plan_hash
            or validated['signed_sha256']!=sign['audit']['sha256']):
        raise ValueError('matching real workload execution not proven')
    remote.python("import hashlib\nfrom pathlib import Path\n"
                  f"assert hashlib.sha256(Path({sign['signed_hap']!r}).read_bytes()).hexdigest()=={sign['audit']['sha256']!r}",timeout=300)
    bundles={json.loads(p.read_text())['host_app']['bundle_name']
             for p in (ROOT/'cases').glob('*/case.json')}
    for other in sorted(bundles):
        remote.hdc(['shell','aa force-stop '+other])
    installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
    if 'install bundle successfully' not in installed:
        raise RuntimeError(installed)
    preparation=None
    if search_history_fixture:
        preparation=install_search_history(remote,case,variant,search_history_fixture,preferences_path or '')
        if preparation['sha256']!=validated.get('fixture',{}).get('sha256'):
            raise ValueError('trial input differs from the validated workload input')
    remote.upload(ROOT/'tools/ui_driver.py','/home/research/ohm-clean/tools/ui_driver.py')
    destination=f'/home/research/ohm-clean/{cid}/{variant}/memory-plan.json'
    remote.upload(plan,destination)
    code="""import hashlib,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools')
from ui_driver import UI
def shell(command):
 p=subprocess.run(['hdc','shell',command],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
"""
    code+=f"plan_file=Path({destination!r})\nassert hashlib.sha256(plan_file.read_bytes()).hexdigest()=={plan_hash!r}\n"
    code+="plan=json.loads(plan_file.read_text());ui=UI(shell,plan['bundle'],plan['ability'])\n"
    remote.python(code+"ui.run([{'op':'stop'},{'op':'launch'}]);ui.run(plan['setup'])\n",timeout=600)
    pids=remote.hdc(['shell','pidof '+bundle]).split()
    if len(pids)!=1 or not pids[0].isdigit():
        raise ValueError('a unique main app process is required')
    # Kernel reads are independent of the normal UI driver. The SSH observer's
    # own memory and system totals can never become the app's PSS value.
    result=capture_window(remote,int(pids[0]),bundle,
                          lambda:remote.python(code+"ui.run(plan['measured']);ui.run(plan['verify'])\n",timeout=600))
    result.update(status='CAPTURED',case=cid,variant=variant,round=round_number,
                  metric='app_pss_bytes',plan_sha256=plan_hash,
                  signed_sha256=sign['audit']['sha256'],
                  # A validation run's fixture does not prove the input was reset
                  # for this trial. Never inherit its hash as preparation proof.
                  fixture_sha256=preparation['sha256'] if preparation else None,
                  input_preparation_verified=bool(preparation),preparation=preparation,
                  performance_verified=False)
    output.mkdir(parents=True,exist_ok=True)
    (output/'capture.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'{cid}/{variant}/round-{round_number}: CAPTURED {result["app_pss_bytes"]} bytes',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    parser.add_argument('--variant',choices=['unfixed','fixed'],required=True)
    parser.add_argument('--round',type=int,default=1)
    parser.add_argument('--remote',default='cityuPC')
    parser.add_argument('--search-history-fixture',type=Path)
    parser.add_argument('--preferences-path')
    args=parser.parse_args()
    case=json.loads((ROOT/'cases'/args.case/'case.json').read_text())
    capture(Remote(args.remote),case,args.variant,args.round,args.search_history_fixture,args.preferences_path)
