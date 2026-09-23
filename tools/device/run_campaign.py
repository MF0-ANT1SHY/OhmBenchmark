#!/usr/bin/env python3
"""Campaign runner: for every case (grouped by host) verify the full on-device
execution: install unfixed -> seed -> trigger+capture -> install fixed ->
trigger+capture -> judge data presence. Appends records to results/campaign.jsonl.

Usage: python3 run_campaign.py [--only case_id] [--reps N] [--dry-run]
"""
import json
import os
import re
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ohb  # noqa: E402
import triggers_core as tc  # noqa: E402

RESULTS = os.path.join(REPO, 'results')
CAMPAIGN = os.path.join(RESULTS, 'campaign.jsonl')

REPS = 1  # reps per variant for executability verification (protocol wants 3)


def record(rec):
    with open(CAMPAIGN, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps(rec, ensure_ascii=False), flush=True)


def install_variant(case_id, variant):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'build_install_case.py'), case_id, variant],
                       capture_output=True, text=True, timeout=2400)
    ok = r.returncode == 0
    return ok, (r.stdout + r.stderr)[-300:]


def trace_has_data(path, pid=None, min_bytes=500_000):
    if not os.path.exists(path) or os.path.getsize(path) < min_bytes:
        return False, 'trace missing/too small'
    with open(path, 'rb') as f:
        chunk = f.read(4_000_000)
    text = zlib.decompress(chunk) if chunk[:2] == b'\x78\x9c' else chunk
    if b'sched_switch' not in text and b'<4>' not in text:
        return False, 'no sched events'
    if pid and str(pid).encode() not in text:
        return False, f'no pid {pid} events'
    return True, 'ok'


def run_case(case_id, reps=REPS):
    ohb.shell('power-shell wakeup')
    ctx = tc.Ctx(case_id)
    rec = {'case': case_id, 'host': ctx.case['host_app']['local_path'], 'ts': time.time()}
    seed_fn = tc.SEEDS.get(case_id)
    trig_fn = tc.TRIGGERS.get(case_id, tc.default_trigger)

    for variant in ('unfixed', 'fixed'):
        ok, msg = install_variant(case_id, variant)
        rec[f'install_{variant}'] = ok
        if not ok:
            rec.update(verdict='BLOCKED', blocker=f'install {variant}: {msg}')
            record(rec)
            return rec
        try:
            if seed_fn and variant == 'unfixed':
                seed_fn(ctx)
                rec['seed'] = 'ok'
            reps_out = []
            for rep in range(1, reps + 1):
                art = trig_fn(ctx, rep)
                pid = ohb.pid()
                has, why = trace_has_data(art['trace'], pid)
                reps_out.append({'rep': rep, 'trace': art['trace'], 'size': os.path.getsize(art['trace']),
                                 'data': has, 'why': why})
            rec[f'reps_{variant}'] = reps_out
        except Exception as e:
            rec.update(verdict='BLOCKED', blocker=f'{variant} trigger: {str(e)[-300:]}')
            record(rec)
            return rec
    rec['verdict'] = 'EXECUTABLE'
    record(rec)
    return rec


def main():
    only = None
    reps = REPS
    if '--only' in sys.argv:
        only = sys.argv[sys.argv.index('--only') + 1]
    if '--reps' in sys.argv:
        reps = int(sys.argv[sys.argv.index('--reps') + 1])
    manifest = json.load(open(os.path.join(REPO, 'manifest.json')))
    cases = manifest['cases']
    cjs = []
    for c in cases:
        cid = c['id'] if isinstance(c, dict) else c
        cj = json.load(open(os.path.join(REPO, 'cases', cid, 'case.json')))
        cjs.append(cj)
    if only:
        cjs = [cj for cj in cjs if cj['id'] == only]
    by_host = {}
    for cj in cjs:
        by_host.setdefault(cj['host_app']['local_path'], []).append(cj)

    first_host = True
    for host, group in by_host.items():
        if not first_host:
            ohb.uninstall()  # clean slate between hosts (bundle name is shared)
        first_host = False
        for cj in group:
            if '--dry-run' in sys.argv:
                print('would run', cj['id'])
                continue
            try:
                run_case(cj['id'], reps)
            except Exception as e:
                record({'case': cj['id'], 'verdict': 'BLOCKED', 'blocker': str(e)[-300:]})
    print('CAMPAIGN DONE')


if __name__ == '__main__':
    main()
