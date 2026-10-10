#!/usr/bin/env python3
"""Regenerate manifest.json from the 30 case.json files."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    cases = []
    for cdir in sorted((ROOT / 'cases').iterdir()):
        cj = cdir / 'case.json'
        if not cdir.is_dir() or not cj.exists():
            continue
        c = json.loads(cj.read_text(encoding='utf-8'))
        cases.append({
            'id': c['id'],
            'host': c['host_app']['name'],
            'bundle_name': c['host_app']['bundle_name'],
            'category': c['category'],
            'android_source_case': c['android_source_case'],
            'scenarios': c['perf_scenarios'],
            'unfixed_commit': c['unfixed_commit'],
            'fixed_commit': c['fixed_commit'],
            'patch': f'cases/{c["id"]}/fix.patch',
            'testcase': f'cases/{c["id"]}/{c["testcase"]["py_file"]}',
            'oracle_metric': c['test_oracle']['metric'],
        })
    manifest = {
        'dataset': 'OhmBenchmark',
        'platform': 'OpenHarmony / HarmonyOS NEXT (ArkTS/ArkUI)',
        'case_count': len(cases),
        'host_count': len({c['host'] for c in cases}),
        'collection': 'cases/collection.yaml',
        'cases': cases,
    }
    (ROOT / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(cases)} cases -> manifest.json')


if __name__ == '__main__':
    main()
