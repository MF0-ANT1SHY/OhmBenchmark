#!/usr/bin/env python3
"""Verify the uniform case structure and the three reproducibility criteria.

Checks, per case:
  1. Required files exist (case.json, fix.patch, testcase/*.py + *.json).
  2. case.json uses the uniform v2 key set and a HapRay PerfTestCase whose
     CASE_ID matches the case id.
  3. The collection block references the shared cases/collection.yaml and its
     modes cover htrace+hiperf (+memory for MemLoad cases).
  4. The oracle names a CPU or memory metric the collection yields, with a
     comparison of unfixed >= fixed.
  5. Git integrity: every case tag exists in the host clone; tag trees match
     hosts_patches/host-reconstruction.json (so the fixed version is provably
     unchanged); fix.patch equals git diff unfixed..fixed.

Usage: python3 tools/verify_case_structure.py
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TOP_KEYS = ['id', 'host_app', 'android_source_case', 'android_mechanism',
            'category', 'bug_description', 'perf_scenarios', 'unfixed_commit',
            'fixed_commit', 'fix_summary', 'build', 'testcase', 'collection',
            'test_oracle', 'reproduction']
TESTCASE_KEYS = ['name', 'py_file', 'descriptor', 'install_dir', 'driver',
                 'module', 'ability', 'trigger']
ORACLE_METRICS = {'hiperf_instructions', 'trace_cpu_ms', 'app_pss_bytes',
                  'nativehook_retained_bytes'}

failures = []


def fail(case, msg):
    failures.append(f'{case}: {msg}')


def git(host_path, *args):
    r = subprocess.run(['git', '-C', str(host_path), *args],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main():
    recon = json.loads((ROOT / 'hosts_patches' / 'host-reconstruction.json')
                       .read_text(encoding='utf-8'))['hosts']
    case_dirs = sorted(d for d in (ROOT / 'cases').iterdir()
                       if d.is_dir() and (d / 'case.json').exists())
    if len(case_dirs) != 30:
        fail('cases', f'{len(case_dirs)} case directories, expected 30')
    for cdir in case_dirs:
        cid = cdir.name
        c = json.loads((cdir / 'case.json').read_text(encoding='utf-8'))
        if c.get('id') != cid:
            fail(cid, 'id field does not match directory name')
        missing = [k for k in TOP_KEYS if k not in c]
        extra = [k for k in c if k not in TOP_KEYS]
        if missing:
            fail(cid, f'missing top-level keys {missing}')
        if extra:
            fail(cid, f'unexpected top-level keys {extra}')

        # --- testcase files ---
        tc = c.get('testcase', {})
        missing = [k for k in TESTCASE_KEYS if k not in tc]
        if missing:
            fail(cid, f'testcase missing keys {missing}')
            continue
        if tc['driver'] != 'DeviceTest':
            fail(cid, f"driver {tc['driver']!r} != DeviceTest")
        py = cdir / tc['py_file']
        js = cdir / tc['descriptor']
        for f in (py, js, cdir / 'fix.patch'):
            if not f.exists():
                fail(cid, f'missing file {f.relative_to(ROOT)}')
        if py.exists():
            tree = ast.parse(py.read_text(encoding='utf-8'))
            cls = [n for n in ast.walk(tree)
                   if isinstance(n, ast.ClassDef) and n.name == tc['name']]
            if not cls:
                fail(cid, f'no class {tc["name"]} in {py.name}')
            else:
                case_id = None
                has_perf = False
                for n in ast.walk(cls[0]):
                    if isinstance(n, ast.Assign) and \
                            any(getattr(t, 'id', '') == 'CASE_ID'
                                for t in n.targets):
                        case_id = getattr(n.value, 'value', None)
                    if isinstance(n, ast.Call) and \
                            getattr(n.func, 'attr', '') == 'execute_performance_step':
                        has_perf = True
                base = getattr(cls[0].bases[0], 'id', '') if cls[0].bases else ''
                if base != 'PerfTestCase':
                    fail(cid, f'{tc["name"]} base is {base!r}, not PerfTestCase')
                if case_id != cid:
                    fail(cid, f'CASE_ID {case_id!r} != {cid!r}')
                if not has_perf:
                    fail(cid, 'no execute_performance_step call')
            name = tc['name']
            if not re.match(r'^(Perf|Mem)Load_[a-z]+_\d{4}$', name):
                fail(cid, f'testcase name {name!r} does not follow HapRay naming')
        if js.exists():
            desc = json.loads(js.read_text(encoding='utf-8'))
            if desc.get('description') != cid:
                fail(cid, 'descriptor description != case id')
            drv = desc.get('driver', {})
            if drv.get('type') != 'DeviceTest':
                fail(cid, 'descriptor driver.type != DeviceTest')
            if Path(tc['py_file']).name not in drv.get('py_file', []):
                fail(cid, 'descriptor py_file does not name the testcase')

        # --- collection ---
        col = c.get('collection', {})
        if col.get('config') != '../collection.yaml':
            fail(cid, f"collection.config {col.get('config')!r}")
        if not (ROOT / 'cases' / 'collection.yaml').exists():
            fail(cid, 'cases/collection.yaml missing')
        modes = set(col.get('modes', []))
        need = {'htrace', 'hiperf'}
        if tc['name'].startswith('MemLoad'):
            need.add('memory')
        if not need <= modes:
            fail(cid, f'collection modes {modes} lack {need - modes}')
        if not isinstance(col.get('step_duration_s'), int):
            fail(cid, 'collection.step_duration_s missing')

        # --- oracle ---
        o = c.get('test_oracle', {})
        if o.get('metric') not in ORACLE_METRICS:
            fail(cid, f"oracle metric {o.get('metric')!r} not a CPU/memory metric")
        if 'unfixed' not in o.get('comparison', ''):
            fail(cid, 'oracle comparison does not compare unfixed to fixed')
        ev = o.get('evidence', {})
        if ev.get('status') not in ('measured', 'supporting', 'expected'):
            fail(cid, f"evidence.status {ev.get('status')!r}")
        if not o.get('mechanism_oracle', {}).get('metric'):
            fail(cid, 'mechanism_oracle lost')

        # --- git integrity ---
        host = Path(c['host_app']['local_path']).name
        hdir = ROOT / 'hosts' / host
        tags = {t: git(hdir, 'rev-parse', t)
                for t in (f'case/{cid}/unfixed', f'case/{cid}/fixed')}
        for t, sha in tags.items():
            if not sha:
                fail(cid, f'{host}: missing tag {t}')
        if tags[f'case/{cid}/unfixed'] and \
                not tags[f'case/{cid}/unfixed'].startswith(c['unfixed_commit']):
            fail(cid, f"unfixed_commit {c['unfixed_commit']} != tag "
                      f"{tags[f'case/{cid}/unfixed'][:7]}")
        if tags[f'case/{cid}/fixed'] and \
                not tags[f'case/{cid}/fixed'].startswith(c['fixed_commit']):
            fail(cid, f"fixed_commit {c['fixed_commit']} != tag "
                      f"{tags[f'case/{cid}/fixed'][:7]}")

        host_recon = recon.get(host, {}).get('case_tags', {})
        for t in tags:
            entry = host_recon.get(t)
            if not entry:
                fail(cid, f'{t} not registered in host-reconstruction.json')
                continue
            tree = git(hdir, 'rev-parse', f'{t}^{{tree}}')
            if tree != entry['tree']:
                fail(cid, f'{t} tree {tree[:8] if tree else None} != '
                          f'reconstruction map {entry["tree"][:8]}')

        patch = (cdir / 'fix.patch')
        if patch.exists() and all(tags.values()):
            expect = git(hdir, 'diff', '--no-color',
                         f'case/{cid}/unfixed', f'case/{cid}/fixed')
            actual = patch.read_text(encoding='utf-8').strip()
            if expect is not None and expect.strip() != actual:
                fail(cid, 'fix.patch differs from git diff unfixed..fixed')

    for f in failures:
        print('FAIL', f)
    print(f'FAILURES: {len(failures)}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
