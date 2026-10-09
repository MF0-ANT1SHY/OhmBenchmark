#!/usr/bin/env python3
"""Collect one instrumented run of a case on the attached device, from WSL.

This is the protocol used by the original Windows collector, reimplemented against
the `hdc` binary available in WSL (3.2.0c). It drives the app's bench entry:

    force-stop -> cold start -> warm start with `--ps bench <case>`
    -> wait state=ready -> start hiperf/hitrace -> touch ohm-go
    -> wait state=done -> stop profilers -> pull trace/perf

It writes into measurements/<case>/<variant>/runN/ the same file names the
original collection used, so downstream tooling is unchanged.

Usage:
    python3 device-tests/collect_wsl.py CASE VARIANT [--run N] [--trace-cats "..."]
"""
import argparse
import gzip
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDC = shutil.which('hdc')


def hdc(*args, timeout=120):
    p = subprocess.run([HDC, *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0 and 'file recv' in ' '.join(args):
        raise RuntimeError(f"hdc {' '.join(args)} failed: {p.stderr.strip()[:200]}")
    return p.stdout.strip()


def sh(cmd, timeout=120):
    return hdc('shell', cmd, timeout=timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('case')
    ap.add_argument('variant', choices=['unfixed', 'fixed'])
    ap.add_argument('--run', type=int, default=1)
    ap.add_argument('--bundle', default=None)
    ap.add_argument('--module', default='entry')
    ap.add_argument('--ability', default='EntryAbility')
    ap.add_argument('--trace-cats', default='app sched disk distributeddatamgr ark')
    ap.add_argument('--hold-seconds', type=float, default=0.0,
                    help='drive UI interactions during the measurement window instead of waiting')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true',
                    help='overwrite an existing run directory (the original collection is evidence)')
    args = ap.parse_args()

    if not HDC:
        sys.exit('hdc not found on PATH')

    spec = json.loads((ROOT / 'cases' / args.case / 'case.json').read_text(encoding='utf-8'))
    bundle = args.bundle or spec['host_app']['bundle_name']
    base = f'/data/app/el2/100/base/{bundle}/haps/{args.module}/files'
    out = ROOT / 'measurements' / args.case / args.variant / f'run{args.run}'

    def status():
        try:
            return json.loads(sh(f'cat {base}/ohm-status.json'))
        except Exception:
            return {}

    def wait_state(state, seconds=300):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            v = status()
            if v.get('state') == state:
                return v
            if v.get('state') == 'error':
                raise RuntimeError(f"app reported error: {v}")
            time.sleep(0.25)
        raise TimeoutError(f'timed out waiting for {state}; last={status()}')

    steps = []

    def rec(cmd):
        steps.append(f'{cmd}\n{sh(cmd)}')

    print(f'case={args.case} variant={args.variant} bundle={bundle}')
    if args.dry_run:
        print(f'  would write to {out}')
        print(f'  status file {base}/ohm-status.json')
        return 0

    if out.exists() and any(out.iterdir()) and not args.force:
        sys.exit(f'refusing to overwrite existing run directory:\n  {out}\n'
                 f'It already holds collected evidence. Pass --force to overwrite, or pick --run N.')
    out.mkdir(parents=True, exist_ok=True)
    rec(f'aa force-stop {bundle}')
    rec(f'rm -f {base}/ohm-status.json {base}/ohm-go')
    rec(f'aa start -a {args.ability} -b {bundle}')
    time.sleep(4)
    rec(f'aa start -a {args.ability} -b {bundle} --ps bench {args.case}')
    v = wait_state('ready')
    print(f'  ready: {v}')

    pid = sh(f'pidof {bundle}').split()[0]
    print(f'  pid={pid}')

    fd_before = None
    if 'fd' in json.dumps(spec['test_oracle']).lower() or args.case.endswith('http_session_leak'):
        fd_before = int(sh(f'ls /proc/{pid}/fd | wc -l'))
        (out / 'fd-before.txt').write_text(sh(f'ls -l /proc/{pid}/fd'), encoding='utf-8')
    (out / 'before.txt').write_text(
        sh(f'cat /proc/{pid}/stat; cat /proc/{pid}/status; cat /sys/class/thermal/thermal_zone0/temp'),
        encoding='utf-8')

    for cmd in [
        f'hiperf record -p {pid} -f 1000 -e sw-cpu-clock -s fp -o /data/local/tmp/ohm-perf.data --control prepare',
        f'hiperf stat -p {pid} -e hw-cpu-cycles,hw-instructions,sw-task-clock,sw-context-switches '
        f'-o /data/local/tmp/ohm-stat.txt --control prepare',
        f'hitrace --trace_begin -b 65536 {args.trace_cats}',
        'hiperf record --control start',
        'hiperf stat --control start',
    ]:
        rec(cmd)

    rec(f'touch {base}/ohm-go')
    started = time.time()
    if args.hold_seconds:
        time.sleep(args.hold_seconds)
    result = wait_state('done')
    elapsed = time.time() - started
    print(f'  done in {elapsed:.1f}s: {result}')

    for cmd in ['hiperf stat --control stop', 'hiperf record --control stop',
                'hitrace --trace_finish -o /data/local/tmp/ohm-trace.txt']:
        rec(cmd)

    (out / 'after.txt').write_text(sh(f'cat /proc/{pid}/stat; cat /proc/{pid}/status'), encoding='utf-8')
    result.update(variant=args.variant, run=args.run, pid=int(pid), bundle=bundle)
    if fd_before is not None:
        result.update(fd_before=fd_before, fd_after=int(sh(f'ls /proc/{pid}/fd | wc -l')))
        (out / 'fd-after.txt').write_text(sh(f'ls -l /proc/{pid}/fd'), encoding='utf-8')
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (out / 'capture.txt').write_text('\n'.join(steps), encoding='utf-8')

    for remote, local in [('ohm-perf.data', 'perf.data'), ('ohm-stat.txt', 'perf-stat.txt'),
                          ('ohm-trace.txt', 'trace.txt')]:
        hdc('file', 'recv', '/data/local/tmp/' + remote, str(out / local))
    with (out / 'trace.txt').open('rb') as f, gzip.open(out / 'trace.txt.gz', 'wb') as z:
        z.write(f.read())
    (out / 'trace.txt').unlink()
    (out / 'hilog.txt').write_text(sh(f'hilog -x -P {pid}'), encoding='utf-8')
    print(f'  wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
