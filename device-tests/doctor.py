#!/usr/bin/env python3
"""Report what this machine can actually do with the benchmark, and what is missing.

Answers the handoff question "can I still build, sign, install and measure?" in one
command, with the evidence for each answer rather than an assumption.

Usage:
    python3 device-tests/doctor.py [--data DIR]
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SDK_LIB = Path('/mnt/c/Users/research/hdc/lib')
SIGNING_ASSETS = Path('/home/research/OhmBenchmark-backup/signing-assets')


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def line(ok, label, detail=''):
    mark = {True: 'OK  ', False: 'NO  ', None: '??  '}[ok]
    print(f'  {mark}{label:<34} {detail}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='/home/research/OhmBenchmark-data')
    args = ap.parse_args()
    data = Path(args.data)

    print('== toolchain ==')
    for tool in ('hdc', 'node', 'java', 'hvigorw', 'ohpm'):
        p = shutil.which(tool)
        line(bool(p), tool, p or 'not on PATH')
    rc, out = run(['java', '-version'])
    if rc == 0:
        line(True, 'java runtime', out.splitlines()[0][:60])

    print('\n== device ==')
    rc, out = run(['hdc', 'list', 'targets'])
    targets = [t for t in out.split() if t and not t.startswith('[')]
    line(bool(targets), 'device attached', ', '.join(targets) or 'none')
    if targets:
        rc, model = run(['hdc', 'shell', 'param', 'get', 'const.product.model'])
        rc2, build = run(['hdc', 'shell', 'param', 'get', 'const.product.software.version'])
        line(True, 'model / build', f'{model.strip()} / {build.strip()}')
        rc3, hitrace = run(['hdc', 'shell', 'which hitrace'])
        line(rc3 == 0 and 'hitrace' in hitrace, 'hitrace on device', hitrace.strip()[:40])

    print('\n== signing ==')
    line(SDK_LIB.exists(), 'SDK signing lib', str(SDK_LIB))
    line((SDK_LIB / 'OpenHarmony.p12').exists(), 'keystore OpenHarmony.p12')
    line((SDK_LIB / 'hap-sign-tool.jar').exists(), 'hap-sign-tool.jar')
    line(SIGNING_ASSETS.exists(), 'checksummed backup copy', str(SIGNING_ASSETS))
    java_ok, _ = run(['java', '-version'])
    line(java_ok == 0, 'can actually run the signer', 'needs a JRE (see SIGNING.md)')

    print('\n== recorded builds and harnesses ==')
    patches = sorted(p.name for p in (REPO / 'device-tests' / 'patches').iterdir() if p.is_dir())
    haps = sorted({p.parent.parent.name for p in data.rglob('app.hap')})
    line(bool(haps), 'signed HAPs available', f'{len(haps)} cases')
    line(bool(patches), 'measurement harness patches', f'{len(patches)} cases')
    ready = sorted(set(patches) & set(haps))
    line(bool(ready), 'ready to measure now', f'{len(ready)} cases: ' + ', '.join(ready[:4]) +
         (' ...' if len(ready) > 4 else ''))

    print('\n== measurement data ==')
    res = data / 'measurements' / 'results.json'
    if res.exists():
        doc = json.loads(res.read_text(encoding='utf-8'))
        import collections
        st = collections.Counter(c['status'] for c in doc['cases'])
        line(True, 'original results.json', ', '.join(f'{v} {k}' for k, v in st.items()))
    else:
        line(False, 'original results.json', 'not found')
    rec = data / 'measurements' / 'results-reconciled.json'
    line(rec.exists(), 'reconciled view', str(rec) if rec.exists() else 'run tools/export_reconciled.py')

    print('\n== what this means ==')
    if java_ok != 0:
        print('  Building and signing NEW HAPs is blocked: no Java runtime.')
        print('  Existing signed builds can still be installed and re-measured.')
    else:
        print('  Signing is available; new harness builds can be signed and deployed.')
    print('  See SIGNING.md for the signing story and docs/analysis/remaining-17-plan.md')
    print('  for the per-case plan.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
