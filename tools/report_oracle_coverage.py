#!/usr/bin/env python3
"""Report how well each case's measurement covers the oracle it declares.

Replaces the hardcoded metric choice in the original exporter
(`cpu_cases={...}; key='trace_cpu_ms' if name in cpu_cases else 'elapsed_ms'`).
Every round already records BOTH elapsed_ms and trace_cpu_ms, and some rounds
carry auxiliary counters, so that choice discarded real measurements and left no
case reporting the metric its cases/<id>/case.json test_oracle declares.

This tool invents no numbers and does not rewrite the authoritative
measurements/results.json. Verdicts:

  satisfied            the collected metric is the declared one
  counter-satisfied    the declared counter was collected as a probe field
  proxy                a different metric was collected; the contract records why
  collected-not-used   a usable primitive was collected but not the declared one
  never-run            no rounds; the contract names the primitive needed

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
ORDER = ['satisfied', 'counter-satisfied', 'declared-collected-new', 'mechanism-absent',
         'proxy', 'collected-not-used', 'never-run']


# Any OHMB/<Name> marker with an integer value counts as a declared-metric reading, so the
# report picks up new instrumentation without needing a list entry. The values below are the
# markers already seen, kept only for readable output.
KNOWN_MARKERS = ('StatementCount', 'QueryCount', 'FlushCount')
MARKER_RE = r'OHMB/([A-Za-z]+)\|(\d+)'


def load_staged(data):
    """Read newly collected runs from measurements-staging/.

    Returns {case: {variant: {marker: [values]}}} for whatever has been collected since the
    original session."""
    import gzip
    import re
    root = data / 'measurements-staging'
    out = {}
    if not root.exists():
        return out
    for case_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for variant_dir in sorted(p for p in case_dir.iterdir() if p.is_dir()):
            for run_dir in sorted(p for p in variant_dir.iterdir() if p.is_dir()):
                trace = run_dir / 'trace.txt.gz'
                if not trace.exists():
                    continue
                try:
                    with gzip.open(trace, 'rt', errors='replace') as f:
                        blob = f.read()
                except OSError:
                    continue
                for marker, value in re.findall(MARKER_RE, blob):
                    out.setdefault(case_dir.name, {}).setdefault(
                        variant_dir.name, {}).setdefault(marker, []).append(int(value))
    return out


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


def classify(case_id, contract, rounds):
    c = contract['cases'][case_id]
    declared, prim = c['oracle_metric'], c['primitive']
    rs = rounds.get(case_id, [])
    base = dict(case=case_id, host=c['host'], declared=declared, primitive=prim)

    if not rs:
        return dict(**base, collected=None, verdict='never-run',
                    detail=f'needs a {prim} primitive; {c["gap"]}')

    if any(declared in r for r in rs):
        return dict(**base, collected=declared, verdict='satisfied', detail='')

    aux = c.get('aux_counters') or []
    if aux and all(all(k in r for k in aux) for r in rs):
        got = '+'.join(aux)
        verdict = 'mechanism-absent' if c.get('mechanism') == 'absent' else 'counter-satisfied'
        return dict(**base, collected=got, verdict=verdict,
                    detail=(c.get('mechanism_note') or c['gap'] or
                            f'declared counter collected as {got}'))

    have = sorted({k for r in rs for k in ('elapsed_ms', 'trace_cpu_ms') if k in r})
    want = PRIMARY.get(prim)
    if want and want in have:
        return dict(**base, collected=want,
                    verdict='satisfied' if want == declared else 'proxy',
                    detail='' if want == declared else c['gap'])
    return dict(**base, collected=None, verdict='collected-not-used',
                detail=f'rounds carry {have}; {prim} primitive needs {want}. {c["gap"]}')


def effect(rounds, key):
    keys = key.split('+')
    if len(keys) != 1:
        return None
    k = keys[0]
    u = sorted(r[k] for r in rounds if r.get('variant') == 'unfixed' and k in r)
    f = sorted(r[k] for r in rounds if r.get('variant') == 'fixed' and k in r)
    if len(u) < 3 or len(f) < 3:
        return None
    return dict(unfixed_median=statistics.median(u), fixed_median=statistics.median(f),
                reduction_percent=(1 - statistics.median(f) / statistics.median(u)) * 100,
                nonoverlapping=max(f) < min(u), n_unfixed=len(u), n_fixed=len(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=str(DATA))
    ap.add_argument('--json')
    ap.add_argument('--md')
    args = ap.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding='utf-8'))
    rounds = load_data()['rounds']
    staged = load_staged(Path(args.data))

    rows = []
    for cid in sorted(contract['cases']):
        row = classify(cid, contract, rounds)
        if row['collected']:
            row['effect'] = effect(rounds.get(cid, []), row['collected'])
        if cid in staged:
            per = staged[cid]
            # report every marker found for this case, keyed by marker name
            found = {}
            for variant, markers in per.items():
                for marker, values in markers.items():
                    found.setdefault(marker, {})[variant] = [max(values)]
            if found:
                row['staged_counts'] = found
                marker = sorted(found)[0]
                row['collected'] = marker
            if row['verdict'] in ('collected-not-used', 'proxy', 'never-run'):
                row['verdict'] = 'declared-collected-new'
        rows.append(row)

    counts = {}
    for r in rows:
        counts[r['verdict']] = counts.get(r['verdict'], 0) + 1

    print('oracle coverage over %d cases' % len(rows))
    for k in ORDER:
        if counts.get(k):
            print(f"  {k:<20} {counts[k]}")
    for title, kinds in (('declared metric collected', ('satisfied', 'counter-satisfied', 'proxy')),
                         ('mechanism does not manifest on this build', ('mechanism-absent',)),
                         ('declared metric newly collected (staged runs)', ('declared-collected-new',)),
                         ('declared primitive collected under another field', ('collected-not-used',)),
                         ('never run on device', ('never-run',))):
        print(f"\n  === {title} ===")
        for r in rows:
            if r['verdict'] in kinds:
                extra = ''
                sc = r.get('staged_counts')
                if sc:
                    parts = []
                    for marker, per_variant in sorted(sc.items()):
                        got = ', '.join(f'{v}={vals}' for v, vals in sorted(per_variant.items()))
                        parts.append(f'{marker}[{got}]')
                    extra = '  staged: ' + ' '.join(parts)
                print(f"    {r['case']:<44} {r['verdict']:<21} {r['primitive']:<8} "
                      f"{r['declared']} -> {r['collected'] or '-'}{extra}")

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
