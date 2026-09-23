#!/usr/bin/env python3
"""Batch runner: build + install + launch-verify one case variant on device.

Usage:
  python3 build_install_case.py <case_id> <unfixed|fixed> [--skip-build]

Writes a JSON status line to results/device_run.jsonl and prints it.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ohb  # noqa: E402

ENV = dict(os.environ)
ENV['PATH'] = os.path.expanduser('~/.local/bin/command-line-tools/bin') + ':' + ENV['PATH']
ENV['DEVECO_SDK_HOME'] = os.path.expanduser('~/.local/bin/command-line-tools/sdk')

RESULTS = os.path.join(REPO, 'results')
os.makedirs(RESULTS, exist_ok=True)


def run(cmd, cwd, timeout=1200):
    r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def main():
    case_id, variant = sys.argv[1], sys.argv[2]
    skip_build = '--skip-build' in sys.argv
    case = json.load(open(os.path.join(REPO, 'cases', case_id, 'case.json')))
    host_dir = os.path.join(REPO, case['host_app']['local_path'])
    commit = case[f'{variant}_commit']
    status = {'case': case_id, 'variant': variant, 'commit': commit, 'ts': time.time()}

    if not skip_build:
        run(['git', 'checkout', '--', '.'], host_dir)  # revert ohpm churn
        rc, out = run(['git', 'checkout', '-q', commit], host_dir)
        if rc:
            status.update(step='checkout', ok=False, err=out[-400:])
            _done(status)
        node_modules = os.path.join(host_dir, 'oh_modules')
        if not os.path.isdir(node_modules):
            rc, out = run(['ohpm', 'install', '--all'], host_dir, timeout=900)
            if rc:
                status.update(step='ohpm', ok=False, err=out[-400:])
                _done(status)
        rc, out = run(['node', os.path.join(HERE, 'inject_signing.cjs'), '.'], host_dir)
        if rc:
            status.update(step='inject', ok=False, err=out[-400:])
            _done(status)
        rc, out = run(['hvigorw', '--mode', 'module', '-p', 'product=default',
                       '-p', 'buildMode=debug', 'assembleHap', '--no-daemon'], host_dir, timeout=1800)
        if rc or 'BUILD SUCCESSFUL' not in out:
            status.update(step='build', ok=False, err=out[-600:])
            _done(status)
        status['build'] = 'ok'

    hap = os.path.join(host_dir, 'entry/build/default/outputs/default/entry-default-signed.hap')
    if not os.path.exists(hap):
        # some hosts use a different module name / output; prefer entry module
        cands = subprocess.run(['find', host_dir, '-name', '*-signed.hap', '-path', '*outputs*'],
                               capture_output=True, text=True).stdout.split()
        entry = [c for c in cands if '/entry/' in c]
        if not cands:
            status.update(step='hap', ok=False, err='no signed hap produced')
            _done(status)
        hap = (entry or cands)[0]
    try:
        try:
            ohb.install(hap)
        except Exception:
            # stale bundle from another host (shared bundle name): clean retry
            ohb.uninstall()
            time.sleep(1)
            ohb.install(hap)
        status['install'] = 'ok'
    except Exception as e:
        status.update(step='install', ok=False, err=str(e)[-400:])
        _done(status)

    try:
        ability = ohb.ability_of(host_dir)
        ohb.force_stop()
        time.sleep(1)
        out = ohb.launch(ability)
        pid = ohb.wait_pid(20)
        time.sleep(3)  # let first page render
        alive = ohb.pid() is not None
        shot = os.path.join(RESULTS, f'{case_id}.{variant}.launch.png')
        ohb.screenshot(shot)
        lay = os.path.join(RESULTS, f'{case_id}.{variant}.launch.json')
        ohb.shell(f'uitest dumpLayout -p /data/local/tmp/ohb_lay.json')
        ohb.hdc('file', 'recv', '/data/local/tmp/ohb_lay.json', lay)
        status.update(step='launch', ok=bool(pid and alive), pid=pid, ability=ability,
                      launch_out=out[:100], screenshot=shot)
    except Exception as e:
        status.update(step='launch', ok=False, err=str(e)[-400:])
        _done(status)
    _done(status)


def _done(status):
    status['ok'] = status.get('ok', status.get('step') in ('launch',) and status.get('ok', False))
    with open(os.path.join(RESULTS, 'device_run.jsonl'), 'a') as f:
        f.write(json.dumps(status, ensure_ascii=False) + '\n')
    print(json.dumps(status, ensure_ascii=False))
    sys.exit(0 if status.get('ok') else 2)


if __name__ == '__main__':
    main()
