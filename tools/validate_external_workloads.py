#!/usr/bin/env python3
"""Validate actual UI actions on each clean variant, with archived device evidence.

This records workload execution, never a CPU/memory improvement verdict. Browser
fixtures are prepared externally for each variant, keeping the comparison data
identical even after destructive actions such as clearing history.
"""
import argparse
import hashlib
import json
import subprocess
import sqlite3
import shlex
import time
import re
from pathlib import Path

from install_sqlite_fixture import install as install_fixture
from remote_device import Remote
from seed_local_songs import deploy as deploy_songs

ROOT = Path(__file__).resolve().parents[1]


def validate(remote, case, variant, browser_fixture=None, local_song_fixture=None):
    cid = case['id']
    folder = ROOT / 'artifacts/clean' / cid / variant
    signed = json.loads((folder / 'sign.json').read_text())
    plan_path = ROOT / 'cases' / cid / case['testcase']['workload']
    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    result = {'case':cid, 'variant':variant, 'signed_sha256':signed['audit']['sha256'],
              'plan_sha256':plan_hash, 'status':'FAIL', 'performance_verified':False}
    try:
        if browser_fixture and local_song_fixture:
            raise ValueError('only one fixture may be supplied')
        if local_song_fixture and case['host_app']['bundle_name']!='cc.chenlvin.cloudmusic':
            raise ValueError('local song fixture provided to a different app')
        remote.python("from pathlib import Path\nimport hashlib\n"
                      f"assert hashlib.sha256(Path({signed['signed_hap']!r}).read_bytes()).hexdigest()=={signed['audit']['sha256']!r}", timeout=300)
        output = remote.hdc(['install','-r',signed['signed_hap']], timeout=180)
        if 'install bundle successfully' not in output:
            raise RuntimeError(output)
        if browser_fixture and cid.startswith('browser_'):
            result['fixture'] = install_fixture(remote, case['host_app']['bundle_name'],
                                                case['testcase']['module'], 'Histories.db', browser_fixture)
            result['fixture']['sha256'] = hashlib.sha256(browser_fixture.read_bytes()).hexdigest()
        if local_song_fixture:
            result['fixture']=deploy_songs(local_song_fixture,remote.host)
            result['fixture']['sha256']=result['fixture']['fixture_sha256']
        destination = f'/home/research/ohm-clean/{cid}/{variant}/workload-plan.json'
        remote.upload(plan_path, destination)
        code = """import hashlib,json,subprocess,sys,time,traceback
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools')
from ui_driver import UI
def shell(command):
 p=subprocess.run(['hdc','shell',command],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
"""
        code += f"plan_path=Path({destination!r});plan=json.loads(plan_path.read_text())\n"
        code += f"assert hashlib.sha256(plan_path.read_bytes()).hexdigest()=={plan_hash!r}\n"
        code += "ui=UI(shell,plan['bundle'],plan['ability'])\nphases={}\n"
        code += "ui.run([{'op':'stop'},{'op':'launch'}])\n"
        code += "try:\n"
        code += " for phase in ['setup','measured','verify']:\n"
        code += "  started=time.monotonic()\n  ui.run(plan[phase])\n"
        code += "  phases[phase]={'elapsed_s':time.monotonic()-started,'layout':ui.layout()}\n"
        code += " result={'phases':phases,'status':'PASS'}\n"
        code += "except Exception as exc:\n"
        code += " result={'phases':phases,'status':'FAIL','error':str(exc)}\n"
        code += " try:result['failure_layout']=ui.layout()\n except Exception:pass\n"
        code += "plan_path.with_name('workload-device.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))\n"
        remote.python(code, timeout=600)
        remote.download(str(Path(destination).with_name('workload-device.json')), folder / 'workload-device.json')
        device = json.loads((folder / 'workload-device.json').read_text())
        if device['status'] != 'PASS':
            raise RuntimeError(device['error'])
        result['phase_elapsed_s'] = {p:r['elapsed_s'] for p,r in device['phases'].items()}
        if cid == 'browser_history_delete_no_transaction':
            db = '/data/app/el2/100/database/com.example.nanvision/entry/rdb/Histories.db'
            if not browser_fixture:
                raise RuntimeError('clear-history validation requires a known fixture')
            with sqlite3.connect(f'file:{browser_fixture.resolve()}?mode=ro',uri=True) as fixture_db:
                tables=[r[0] for r in fixture_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='date_table' OR name LIKE 'history_%')")]
            if not tables or any(not re.fullmatch(r'date_table|history_[0-9_]+',t) for t in tables):
                raise RuntimeError('unexpected history fixture schema')
            sql='SELECT '+'+'.join(f'(SELECT COUNT(*) FROM {t})' for t in tables)+';'
            deadline=time.monotonic()+120
            while True:
                remaining = remote.hdc(['shell', f'sqlite3 {db} {shlex.quote(sql)}']).strip()
                if remaining=='0':break
                if not remaining.isdigit() or time.monotonic()>deadline:
                    raise RuntimeError(f'clear-history UI left database rows: {remaining}')
                time.sleep(.1)
            result['functional_check'] = 'all history rows and dates cleared through the production UI'
            result['cleared_tables'] = len(tables)
        result['status'] = device['status']
        result['capture_duration_required_s'] = round(result['phase_elapsed_s']['measured'] + 5)
    except Exception as exc:
        result['error'] = str(exc)
    (folder / 'workload.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(f"{cid}/{variant}: {result['status']} {result.get('error','')}", flush=True)
    return result['status']=='PASS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases',nargs='+')
    parser.add_argument('--remote',default='cityuPC')
    fixtures=parser.add_mutually_exclusive_group()
    fixtures.add_argument('--browser-fixture',type=Path)
    fixtures.add_argument('--local-song-fixture',type=Path)
    args=parser.parse_args()
    remote=Remote(args.remote)
    remote.upload(ROOT/'tools/ui_driver.py','/home/research/ohm-clean/tools/ui_driver.py')
    failed=False
    for cid in args.cases:
        case=json.loads((ROOT/'cases'/cid/'case.json').read_text())
        for variant in ('unfixed','fixed'):
            failed |= not validate(remote,case,variant,args.browser_fixture,args.local_song_fixture)
    return int(failed)


if __name__=='__main__':
    raise SystemExit(main())
