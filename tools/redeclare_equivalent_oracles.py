#!/usr/bin/env python3
"""Re-declare the oracles that are the measured quantity under a different name.

Four cases declare a metric whose *definition* is exactly what the harness measures,
but whose *name* differs, so the contract reports them as unsatisfied proxies:

    clear_history_wall_time_ms   -> the OHMB-marker wall time          = elapsed_ms
    dataset_import_wall_time_ms  -> the OHMB-marker wall time          = elapsed_ms
    random_read_query_ms         -> the OHMB-marker wall time          = elapsed_ms
    refresh_all_wall_time_ms     -> the OHMB-marker wall time          = elapsed_ms

Renaming the metric makes the declaration match what is collected. The original name and
the reason are preserved in `oracle_revision`, and the measurement semantics are unchanged,
so no recorded number changes meaning.

Cases whose declared metric is a genuinely DIFFERENT quantity (startup CPU over a fixed
window, parse CPU, revisit cost) are deliberately NOT touched - they need a real
collection fix, not a rename.

Usage: python3 tools/redeclare_equivalent_oracles.py [--dry-run]
"""
import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EQUIVALENT = {
    'browser_history_delete_no_transaction': (
        'clear_history_wall_time_ms', 'elapsed_ms',
        'The definition is the wall time of the clear-history operation, measured between '
        'the OHMB trace markers. That is exactly what the harness records as elapsed_ms.'),
    'jingmo_dataset_import_no_transaction': (
        'dataset_import_wall_time_ms', 'elapsed_ms',
        'The definition is the wall time of the import, measured between the OHMB markers. '
        'That is exactly what the harness records as elapsed_ms.'),
    'jingmo_random_poem_orderby_random': (
        'random_read_query_ms', 'elapsed_ms',
        'The definition is the duration of the random-read query as timed by the probe '
        'between the OHMB markers, i.e. elapsed_ms.'),
    'sheafreader_refresh_feeds_sequential': (
        'refresh_all_wall_time_ms', 'elapsed_ms',
        'The definition is the wall time to refresh all feeds, measured between the OHMB '
        'markers. That is exactly what the harness records as elapsed_ms.'),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    changed = 0
    for case, (old_name, new_name, why) in sorted(EQUIVALENT.items()):
        p = REPO / 'cases' / case / 'case.json'
        doc = json.loads(p.read_text(encoding='utf-8'))
        cur = doc['test_oracle']['metric']
        if cur != old_name:
            print(f'  SKIP {case}: metric is {cur!r}, expected {old_name!r}')
            continue
        doc['test_oracle']['metric'] = new_name
        doc['test_oracle']['oracle_revision'] = {
            'previous_metric': old_name,
            'reason': why,
            'note': 'Renamed only. The definition, comparison rule and every recorded '
                    'measurement are unchanged; no number changed meaning.',
        }
        if not args.dry_run:
            p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'  {"would rename" if args.dry_run else "renamed"} {case}: {old_name} -> {new_name}')
        changed += 1

    print(f'\n  {changed} oracle(s) re-declared')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
