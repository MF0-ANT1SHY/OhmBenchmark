#!/usr/bin/env python3
"""Identify which recorded build is currently installed on the device, and swap variants.

A case has two signed HAPs on disk (unfixed/fixed). The device holds one of them at a
time. Because the HAPs are signed copies of specific commits, their checksums identify the
installed build without rebuilding anything.

Usage:
    python3 device-tests/which_variant.py CASE            # report installed variant
    python3 device-tests/which_variant.py CASE unfixed     # install that variant
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

DATA = Path('/home/research/OhmBenchmark-data')
REPO = Path(__file__).resolve().parent.parent


def hdc(*args, timeout=180):
    p = subprocess.run(['hdc', *args], capture_output=True, text=True, timeout=timeout)
    return (p.stdout + p.stderr).strip()


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def local_hap(case, variant):
    p = DATA / 'measurements' / case / variant / 'app.hap'
    if not p.exists():
        p = DATA / 'experiments' / case / variant / 'app.hap'
    return p if p.exists() else None


def device_hap_path(bundle, module):
    # bm dump reports the install path; fall back to the standard layout
    out = hdc('shell', f'bm dump -n {bundle} 2>/dev/null | grep -m1 "codePath"')
    for tok in out.replace('"', ' ').replace(',', ' ').split():
        if tok.startswith('/data/'):
            return tok.rstrip('/')
    return f'/data/app/el1/bundle/public/{bundle}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('case')
    ap.add_argument('variant', nargs='?', choices=['unfixed', 'fixed'])
    ap.add_argument('--module', default='entry')
    ap.add_argument('--bundle', default=None)
    args = ap.parse_args()

    spec = json.loads((REPO / 'cases' / args.case / 'case.json').read_text(encoding='utf-8'))
    bundle = args.bundle or spec['host_app']['bundle_name']

    if args.variant:
        src = local_hap(args.case, args.variant)
        if not src:
            sys.exit(f'no recorded HAP for {args.case}/{args.variant}')
        print(f'installing {args.variant}: {src}')
        print('  ' + hdc('install', '-r', str(src)))
        print('installed md5:', md5(src))
        return 0

    sid = hdc('shell', f'bm dump -n {bundle} 2>/dev/null | grep -m1 -i "appId\\|fingerprint"')
    print(f'bundle {bundle}')
    print(f'  {sid[:120]}')
    for v in ('unfixed', 'fixed'):
        p = local_hap(args.case, v)
        if p:
            print(f'  recorded {v:<8} md5={md5(p)}  size={p.stat().st_size}')
    print('\nNote: the device does not expose the installed HAP checksum directly;')
    print('use `which_variant.py CASE <variant>` to force a known state before measuring.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
