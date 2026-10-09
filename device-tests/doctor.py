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
TOOLCHAIN_LIB = (REPO / 'toolchain' / 'command-line-tools' / 'sdk' / 'default' /
                 'openharmony' / 'toolchains' / 'lib')
FALLBACK_LIB = Path.home() / 'OhmBenchmark-toolchain' / 'command-line-tools' / 'sdk' / \
    'default' / 'openharmony' / 'toolchains' / 'lib'
SDK_LIB = TOOLCHAIN_LIB if (TOOLCHAIN_LIB / 'hap-sign-tool.jar').exists() else FALLBACK_LIB
SIGNING_ASSETS = Path('/home/research/OhmBenchmark-backup/signing-assets')


TC_BIN = (REPO / 'toolchain' / 'command-line-tools' / 'bin')
if TC_BIN.exists():
    import os
    os.environ['PATH'] = f'{TC_BIN}{os.pathsep}' + os.environ.get('PATH', '')


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
    line(SDK_LIB.exists(), 'signing lib (toolchain)', str(SDK_LIB))
    line((SDK_LIB / 'OpenHarmony.p12').exists(), 'keystore OpenHarmony.p12')
    line((SDK_LIB / 'hap-sign-tool.jar').exists(), 'hap-sign-tool.jar')
    line(SIGNING_ASSETS.exists(), 'checksummed backup copy', str(SIGNING_ASSETS))
    java_ok, _ = run(['java', '-version'])
    line(java_ok == 0, 'java runtime present')
    # A JRE is not the same as a working signer. Exercise sign-app with the identity
    # prepared by sign_hap_wsl.py, on a real unsigned HAP, so this reports the true
    # capability instead of a proxy.
    hs = Path.home() / '.local' / 'ohsign2'
    chain = hs / 'app.pem'
    profile = next(iter(hs.glob('*.p7b')), None) if hs.exists() else None
    unsigned = next((REPO / 'hosts').rglob('*-unsigned.hap'), None)
    if java_ok != 0:
        line(False, 'sign-app actually works', 'no JRE')
    elif not (chain.exists() and profile and unsigned):
        line(None, 'sign-app actually works',
             'not probed: need sign_hap_wsl.py prepare and an unsigned HAP')
    else:
        try:
            r = subprocess.run(
                ['java', '-jar', str(SDK_LIB / 'hap-sign-tool.jar'), 'sign-app',
                 '-mode', 'localSign', '-keyAlias', 'oh-bench2', '-keyPwd', '123456',
                 '-appCertFile', str(chain), '-profileFile', str(profile),
                 '-inFile', str(unsigned), '-signAlg', 'SHA256withECDSA',
                 '-keystoreFile', str(hs / 'ks.p12'), '-keystorePwd', '123456',
                 '-outFile', '/tmp/doctor-probe.hap'],
                capture_output=True, text=True, timeout=180)
            blob = r.stdout + r.stderr
            if r.returncode == 0 and Path('/tmp/doctor-probe.hap').exists():
                line(True, 'sign-app actually works', 'signed a HAP successfully')
            else:
                msg = [l for l in blob.strip().splitlines() if l.strip()][-1][:64]
                line(False, 'sign-app actually works', msg)
        except Exception as e:  # noqa: BLE001
            line(None, 'sign-app actually works', str(e)[:64])

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
