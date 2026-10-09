#!/usr/bin/env python3
"""Report how well each case's measurement covers the oracle it declares.

Background: the original exporter chose the reported metric from a hardcoded set
(`cpu_cases={...}; key='trace_cpu_ms' if name in cpu_cases else 'elapsed_ms'`).
Every round already records BOTH elapsed_ms and trace_cpu_ms, and some rounds
carry auxiliary counters as well, so the hardcoded choice discarded real
measurements and left no case reporting the metric its cases/<id>/case.json
test_oracle declares.

This tool invents no numbers and does not rewrite the authoritative
measurements/results.json. It reads the recorded rounds, resolves each case
against cases/measurement-contract.json, and classifies it:

  satisfied            the collected metric is the declared one
  counter-satisfied    the declared counter was collected under a probe field name
  proxy                a different metric was collected; the contract records why
  collected-not-used   a usable primitive was collected but not the declared one
  metric-not-collected the needed primitive exists but was not derived for this case
  never-run            no rounds recorded; the contract names the primitive needed
  primitive-missing    needs a primitive that does not exist yet

Usage:
    python3 tools/report_oracle_coverage.py [--json OUT] [--md OUT]
"""
import argparse
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO.parent / 'OhmBenchmark-data'
CONTRACT = REPO / 'cases' / 'measurement-contract.json'

PRIMARY = {'elapsed': 'elapsed_ms', 'cpu': 'trace_cpu_ms', 'count': None, 'external': None}
UNBUILT = {'count', 'external'}
# Counters already emitted by probes into the round records, keyed by contract field.
AUX_ALIASES = {
    'article_components_created': 'article_components_created',
    'history_components_created': 'component_build_count_and_first_frame_ms',
    'retained_fds_and_connections': ('fd_before', 'fd_after'),
}


def load_data():
    out = {'rounds': {}, 'results': {}}
    for name in ('results.json', 'summary.json'):
        p = DATA / 'measurements' / name
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding='utf-8'))
        if name == 'results.json':
            out['results'] = {c['case']: c for c in doc['cases']}
        else:
            for r in doc:
                out['rounds'].setdefault(r['case'], []).append(r)
    return out


def aux_present(rs):
    keys = set()
    for r in rs:
        keys |= {k for k in r if k not in ('case', 'variant', 'run') and not k.startswith('perf_')}
    return keys


def classify(case_id, contract, rounds):
    c = contract['cases'][case_id]
    declared, prim = c['oracle_metric'], c['primitive']
    rs = rounds.get(case_id, [])
    base = dict(case=case_id, host=c['host'], declared=declared, primitive=prim)

    if not rs:
        return dict(**base, collected=None, verdict='never-run',
                    detail=(f'needs a {prim} primitive' +
                            (' that is not built yet' if prim in UNBUILT else '')))

    # 1) exact declared name collected directly
    if any(declared in r for r in rs):
        return dict(**base, collected=declared, verdict='satisfied', detail='')
    # 2) declared counter collected under a probe field alias
    alias = AUX_ALIASES.get(c['probe_field'])
    if alias:
        need = (alias,) if isinstance(alias, str) else tuple(alias)
        if all(all(k in r for k in need) for r in rs):
            got = '+'.join(need)
            return dict(**base, collected=got, verdict='counter-satisfied',
                        detail=f'declared counter collected as {got}')
    # 3) preferred metric for the primitive
    have = sorted({k for r in rs for k in ('elapsed_ms', 'trace_cpu_ms') if k in r})
    want = PRIMARY.get(prim)
    if want and want in have:
        return dict(**base, collected=want,
                    verdict='satisfied' if want == declared else 'proxy',
                    detail='' if want == declared else c['gap'])
    if have:
        return dict(**base, collected=None, verdict='collected-not-used',
                    detail=f'rounds carry {have}; {prim} primitive needs {want}. {c["gap"]}')
    return dict(**base, collected=None, verdict='metric-not-collected', detail=c['gap'])


def effect(rounds, key):
    if '+' in key:
        return None
    u = sorted(r[key] for r in rounds if r.get('variant') == 'unfixed' and key in r)
    f = sorted(r[key] for r in rounds if r.get('variant') == 'fixed' and key in r)
    if len(u) < 3 or len(f) < 3:
        return None
    return dict(unfixed_median=statistics.median(u), fixed_median=statistics.median(f),
                reduction_percent=(1 - statistics.median(f) / statistics.median(u)) * 100,
                nonoverlapping=max(f) < min(u), n_unfixed=len(u), n_fixed=len(f))


ORDER = ['satisfied', 'counter-satisfied', 'proxy', 'collected-not-used',
         'metric-not-collected', 'never-run', 'primitive-missing']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    ap.add_argument('--md')
    args = ap.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding='utf-8'))
    data = load_data()
    rounds = data['rounds']

    rows = []
    for cid in sorted(contract['cases']):
        row = classify(cid, contract, rounds)
        if row['collected']:
            row['effect'] = effect(rounds.get(cid, []), row['collected'])
        rows.append(row)

    counts = {}
    for r in rows:
        counts[r['verdict']] = counts.get(r['verdict'], 0) + 1

    print('oracle coverage over %d cases' % len(rows))
    for k in ORDER:
        if counts.get(k):
            print(f"  {k:<20} {counts[k]}")
    sec = [('declared metric collected', ('satisfied', 'counter-satisfied', 'proxy')),
           ('declared primitive collected under another name', ('collected-not-used',)),
           ('needs a primitive that is not derived/collected yet', ('metric-not-collected', 'never-run'))]
    for title, kinds in sec:
        print(f"\n  === {title} ===")
        for r in rows:
            if r['verdict'] in kinds:
                col = r['collected'] or '-'
                print(f"    {r['case']:<44} {r['verdict']:<19} {r['primitive']:<8} {r['declared']} -> {col}")

    if args.json:
        Path(args.json).write_text(json.dumps({'counts': counts, 'cases': rows},
                                              indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f"\nwrote {args.json}")
    if args.md:
        L = ['# Oracle coverage', '',
             f"Of {len(rows)} cases: " + ', '.join(f'{counts.get(k,0)} {k}' for k in ORDER if counts.get(k)) + '.',
             '', '| case | verdict | primitive | declared metric | collected metric |',
             '| --- | --- | --- | --- | --- |']
        for r in rows:
            L.append(f"| `{r['case']}` | {r['verdict']} | {r['primitive']} | "
                     f"`{r['declared']}` | {('`'+r['collected']+'`') if r['collected'] else '—'} |")
        Path(args.md).write_text('\n'.join(L) + '\n', encoding='utf-8')
        print(f"wrote {args.md}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
