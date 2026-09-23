#!/usr/bin/env python3
"""Per-case proof loop (the executable->triggerable upgrade):

  build+install unfixed -> seed -> 3x (trigger inside capture)
  build+install fixed  -> 3x (trigger inside capture)
  -> judge against cases/<id>/case.json test_oracle (medians of 3 reps)
  -> append one record to results/proof.jsonl

Usage: python3 run_proof.py <case_id> [--reps N] [--skip-seed] [--skip-build-un]
"""
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ohb  # noqa: E402
import triggers_core as tc  # noqa: E402
import proof_metrics  # noqa: E402

RESULTS = os.path.join(REPO, 'results')
PROOF = os.path.join(RESULTS, 'proof.jsonl')


def record(rec):
    with open(PROOF, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def install_variant(case_id, variant, skip_build=False):
    cmd = [sys.executable, os.path.join(HERE, 'build_install_case.py'), case_id, variant]
    if skip_build:
        cmd.append('--skip-build')
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    tail = (r.stdout + r.stderr)[-400:]
    return r.returncode == 0, tail


def run_case(case_id, reps=3, skip_seed=False):
    ohb.shell('power-shell wakeup')
    ctx = tc.Ctx(case_id)
    seed_fn = tc.SEEDS.get(case_id)
    trig_fn = tc.TRIGGERS.get(case_id, tc.default_trigger)
    out = {'case': case_id, 'ts': time.time(), 'reps': reps}

    for variant in ('unfixed', 'fixed'):
        skip_build = variant == 'unfixed' and '--skip-build-un' in sys.argv
        ok, msg = install_variant(case_id, variant, skip_build)
        out[f'install_{variant}'] = ok
        if not ok:
            out.update(verdict='BLOCKED', blocker=f'install {variant}: {msg}')
            record(out)
            return out
        arts = []
        try:
            if seed_fn and variant == 'unfixed' and not skip_seed:
                t0 = time.time()
                out['seed'] = seed_fn(ctx)
                out['seed_seconds'] = round(time.time() - t0)
            for rep in range(1, reps + 1):
                ohb.shell('power-shell wakeup')
                a = trig_fn(ctx, rep)
                a['variant'] = variant
                a['rep'] = rep
                a['pid'] = ohb.pid()
                arts.append(a)
                out.setdefault(f'artifacts_{variant}', []).append(
                    {k: a[k] for k in ('trace', 'hilog', 'rep')})
        except Exception as e:
            out.setdefault(f'artifacts_{variant}', []).extend(
                {k: a[k] for k in ('trace', 'hilog', 'rep')} for a in arts)
            out.update(verdict='BLOCKED', blocker=f'{variant}: {str(e)[-260:]}')
            record(out)
            return out
        out[f'data_{variant}'] = proof_metrics.measure_all(case_id, arts, variant)

    verdict = proof_metrics.judge(case_id, out['data_unfixed'], out['data_fixed'])
    out.update(verdict)
    record(out)
    return out


def main():
    case_id = sys.argv[1]
    reps = 3
    if '--reps' in sys.argv:
        reps = int(sys.argv[sys.argv.index('--reps') + 1])
    rec = run_case(case_id, reps, skip_seed='--skip-seed' in sys.argv)
    print(json.dumps(rec, ensure_ascii=False, indent=1)[:2000])


if __name__ == '__main__':
    main()
