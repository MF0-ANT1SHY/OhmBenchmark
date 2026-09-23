#!/usr/bin/env python3
"""Re-measure + re-judge the artifacts of an existing proof.jsonl record and
append a corrected record (used when a tooling fix lands mid-run; the raw
traces/hilogs are valid, only the judging was wrong).

Usage: python3 rejudge.py <case_id> [record_index_from_end] [--judge-only]

Use --judge-only when only the pass criterion changed. It keeps the stored
per-repetition measurements and avoids rescanning multi-gigabyte traces.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import proof_metrics  # noqa: E402

RESULTS = os.path.join(REPO, 'results')
PROOF = os.path.join(RESULTS, 'proof.jsonl')


def main():
    case_id = sys.argv[1]
    args = [a for a in sys.argv[2:] if a != '--judge-only']
    from_end = int(args[0]) if args else 1
    judge_only = '--judge-only' in sys.argv
    recs = [json.loads(l) for l in open(PROOF)]
    matches = [r for r in recs if r['case'] == case_id]
    if from_end < 1 or from_end > len(matches):
        raise SystemExit(f'{case_id}: only {len(matches)} record(s); requested {from_end} from end')
    rec = matches[-from_end]
    out = dict(rec)
    out['ts'] = __import__('time').time()
    if not judge_only:
        for v in ('unfixed', 'fixed'):
            arts = rec.get(f'artifacts_{v}', [])
            out[f'data_{v}'] = proof_metrics.measure_all(case_id, arts, v)
    out.update(proof_metrics.judge(case_id, out['data_unfixed'], out['data_fixed']))
    out['note'] = ('rejudged from stored per-repetition measurements after oracle fix'
                   if judge_only else 'rejudged offline from original artifacts after tooling fix')
    with open(PROOF, 'a') as f:
        f.write(json.dumps(out, ensure_ascii=False) + '\n')
    print(json.dumps({'case': out['case'], 'verdict': out['verdict'],
                      'evidence': out.get('evidence')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
