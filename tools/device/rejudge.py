#!/usr/bin/env python3
"""Re-measure + re-judge the artifacts of an existing proof.jsonl record and
append a corrected record (used when a tooling fix lands mid-run; the raw
traces/hilogs are valid, only the judging was wrong).

Usage: python3 rejudge.py <case_id> [record_index_from_end]
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
    from_end = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    recs = [json.loads(l) for l in open(PROOF)]
    idx = next(i for i, r in enumerate(recs) if r['case'] == case_id and
               (from_end == 0 or i >= len(recs) - from_end))
    rec = recs[idx]
    out = dict(rec)
    out['ts'] = __import__('time').time()
    for v in ('unfixed', 'fixed'):
        arts = rec.get(f'artifacts_{v}', [])
        out[f'data_{v}'] = proof_metrics.measure_all(case_id, arts, v)
    out.update(proof_metrics.judge(case_id, out['data_unfixed'], out['data_fixed']))
    out['note'] = 'rejudged offline from original artifacts after tooling fix'
    with open(PROOF, 'a') as f:
        f.write(json.dumps(out, ensure_ascii=False) + '\n')
    print(json.dumps({'case': out['case'], 'verdict': out['verdict'],
                      'evidence': out.get('evidence')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
