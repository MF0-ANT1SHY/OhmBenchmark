#!/usr/bin/env python3
"""Build a corrected per-case results view from the recorded rounds.

The original device-tests/export_results.py chose the reported metric from a hardcoded
set, so 14 of the 17 measured cases reported `elapsed_ms` even when their
cases/<id>/case.json test_oracle declares a count or a CPU time. Every round already
records both `elapsed_ms` and `trace_cpu_ms`, and some rounds carry auxiliary counters.

This tool re-derives the per-case numbers from the recorded rounds, pinning the primary
metric to cases/measurement-contract.json, and writes a NEW file:

    measurements/results-reconciled.json

It never modifies measurements/results.json or summary.json, which remain the record of
what the original session actually reported. Rows carry an explicit `oracle` object
stating what was declared, what was used, and whether the declared metric was collected,
so nothing is silently substituted.

Usage:
    python3 tools/export_reconciled.py [--repo DIR] [--data DIR]
"""
import argparse
import json
import statistics
from pathlib import Path

DEFAULT_REPO = Path('/home/research/OhmBenchmark-main')
DEFAULT_DATA = Path('/home/research/OhmBenchmark-data')

# Which recorded field answers each primitive. None => not collected by any harness yet.
PRIMARY = {'elapsed': 'elapsed_ms', 'cpu': 'trace_cpu_ms', 'count': None, 'external': None}


def load(repo, data):
    contract = json.loads((repo / 'cases' / 'measurement-contract.json').read_text(encoding='utf-8'))
    summary = json.loads((data / 'measurements' / 'summary.json').read_text(encoding='utf-8'))
    rounds = {}
    for r in summary:
        rounds.setdefault(r['case'], []).append(r)
    return contract, rounds


def series(rounds, variant):
    return sorted((r for r in rounds if r.get('variant') == variant), key=lambda r: r['run'])


def pick_metric(case, contract, rs):
    """Return (field, oracle_status). Prefers the contract's primitive, then the declared key."""
    c = contract['cases'][case]
    declared = c['oracle_metric']
    have = {k for r in rs for k in ('elapsed_ms', 'trace_cpu_ms') if k in r}
    aux = c.get('aux_counters') or []

    # a counter the probe already emitted, present on every round
    if aux and all(all(k in r for k in aux) for r in rs):
        return '+'.join(aux), ('mechanism-absent' if c.get('mechanism') == 'absent'
                               else 'counter-collected')
    want = PRIMARY.get(c['primitive'])
    if want and want in have:
        return want, ('satisfied' if want == declared else 'proxy')
    if 'elapsed_ms' in have:
        return 'elapsed_ms', 'fallback'
    return None, 'not-collected'


def measure(rs, field):
    keys = field.split('+')
    if len(keys) != 1:
        return None
    k = keys[0]
    u = [r[k] for r in rs if r.get('variant') == 'unfixed' and k in r]
    f = [r[k] for r in rs if r.get('variant') == 'fixed' and k in r]
    if not u or not f:
        return None
    out = {
        'unfixed': u, 'fixed': f,
        'unfixed_median': statistics.median(u), 'fixed_median': statistics.median(f),
        'reduction_percent': (1 - statistics.median(f) / statistics.median(u)) * 100,
    }
    if len(u) >= 3 and len(f) >= 3:
        out['nonoverlapping'] = max(f) < min(u)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=str(DEFAULT_REPO))
    ap.add_argument('--data', default=str(DEFAULT_DATA))
    args = ap.parse_args()
    repo, data = Path(args.repo), Path(args.data)

    contract, rounds = load(repo, data)
    original = {}
    rp = data / 'measurements' / 'results.json'
    if rp.exists():
        original = {c['case']: c for c in json.loads(rp.read_text(encoding='utf-8'))['cases']}

    cases = []
    for cid in sorted(contract['cases']):
        rs = rounds.get(cid, [])
        c = contract['cases'][cid]
        rec = {
            'case': cid,
            'measurement_status': c['measurement_status'],
            'rounds_recorded': len(rs),
            'oracle': {
                'declared_metric': c['oracle_metric'],
                'primitive': c['primitive'],
                'mechanism': c.get('mechanism', 'present'),
                'gap': c['gap'],
            },
        }
        if rs:
            field, status = pick_metric(cid, contract, rs)
            rec['oracle']['metric_used'] = field
            rec['oracle']['status'] = status
            if field:
                m = measure(rs, field)
                if m:
                    rec['measured'] = m
            rec['originally_reported_metric'] = original.get(cid, {}).get('metric')
            rec['per_round'] = {
                'unfixed': [{'run': r['run'], 'elapsed_ms': r.get('elapsed_ms'),
                             'trace_cpu_ms': r.get('trace_cpu_ms'),
                             **{k: r[k] for k in (c.get('aux_counters') or []) if k in r}}
                            for r in series(rs, 'unfixed')],
                'fixed': [{'run': r['run'], 'elapsed_ms': r.get('elapsed_ms'),
                           'trace_cpu_ms': r.get('trace_cpu_ms'),
                           **{k: r[k] for k in (c.get('aux_counters') or []) if k in r}}
                          for r in series(rs, 'fixed')],
            }
        cases.append(rec)

    doc = {
        '$comment': 'Reconciled view derived from the recorded rounds by '
                    'tools/export_reconciled.py. Does NOT replace measurements/results.json. '
                    'Rows state the declared oracle, the metric used, and whether the declared '
                    'metric was actually collected.',
        'device': json.loads(rp.read_text(encoding='utf-8')).get('device') if rp.exists() else None,
        'case_count': len(cases),
        'cases': cases,
    }
    out = data / 'measurements' / 'results-reconciled.json'
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'wrote {out}')

    # summary
    import collections
    st = collections.Counter(c['oracle'].get('status', 'never-run') for c in cases)
    print('  oracle status:', dict(st))
    print()
    print(f"  {'case':<46} {'used':<28} {'status':<18} reduction")
    for c in cases:
        if 'measured' in c:
            m = c['measured']
            print(f"  {c['case']:<46} {str(c['oracle']['metric_used']):<28} "
                  f"{c['oracle']['status']:<18} {m['reduction_percent']:+7.2f}%"
                  f"{'  nonoverlap' if m.get('nonoverlapping') else ''}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
