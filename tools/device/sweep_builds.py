#!/usr/bin/env python3
"""Sweep all cases: build+install+launch verify, grouped by host (so the shared
bundle's data lifetime follows the benchmark's per-host protocol).
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

manifest = json.load(open(os.path.join(REPO, 'manifest.json')))
cases = manifest['cases'] if isinstance(manifest['cases'], list) else manifest['cases']

by_host = {}
for c in cases:
    cid = c['id'] if isinstance(c, dict) else c
    cj = json.load(open(os.path.join(REPO, 'cases', cid, 'case.json')))
    by_host.setdefault(cj['host_app']['local_path'], []).append(cj)

log = open(os.path.join(REPO, 'results', 'sweep.log'), 'a')
total = sum(len(v) for v in by_host.values())
done = 0
for host, cjs in sorted(by_host.items()):
    for cj in cjs:
        for variant in ('unfixed', 'fixed'):
            t0 = time.time()
            r = subprocess.run([sys.executable, os.path.join(HERE, 'build_install_case.py'), cj['id'], variant],
                               capture_output=True, text=True, timeout=2400)
            line = f'[{done + 1}/{total * 2}] {cj["id"]} {variant} rc={r.returncode} {round(time.time() - t0)}s'
            print(line, flush=True)
            log.write(line + '\n')
            log.flush()
            if r.returncode != 0:
                log.write((r.stdout + r.stderr)[-1500:] + '\n')
                log.flush()
        done += 1
print('SWEEP DONE')
