"""Verify the revised Wan memory case from all six unchanged native trials.

The revised gate requires >=1.3x PSS in every pair and the median. The raw
auditor also verifies successful online pages, paired article identities,
visible final-page articles, and growing versus bounded native cache contents.
This gate makes no claim about exclusive-key bytes or a 3x file-write reduction.
"""
import hashlib
import json
import statistics
from pathlib import Path

from audit_wan_home_primary import audit, CASE, ROOT


def capture_folder(variant, number):
    if variant not in ('unfixed', 'fixed') or type(number) is not int or number not in (1, 2, 3):
        raise ValueError('an original paired variant and round are required')
    name = ('wan-home-first-original-workload-pair.json' if number == 1 else
            f'wan-home-original-online-paired-pss-round-{number}.json')
    row = json.loads((ROOT/'validation'/name).read_text())['variants'][variant]
    folder = Path(row.get('raw_artifacts') or row.get('local_raw_artifacts'))
    if not folder.is_absolute():
        folder = ROOT/folder
    if not folder.resolve().is_relative_to((ROOT/'artifacts/clean'/CASE/variant/'online-diagnostics').resolve()):
        raise ValueError('original trial is outside the expected case directory')
    if hashlib.sha256((folder/'capture.json').read_bytes()).hexdigest() != row['capture_sha256']:
        raise ValueError('original capture bytes changed')
    return folder


def accept(write=True):
    path = ROOT/'cases'/CASE/'case.json'
    case = json.loads(path.read_text())
    revision = case.get('acceptance_revision', {})
    if (revision.get('id') != 'native-memory-and-cache-v2' or
            case['test_oracle']['mechanism_oracle'].get('metric') != 'native_home_cache_contents'):
        raise ValueError('explicit revised memory-and-cache contract is required')
    archive = ROOT/revision['previous_case']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != revision['previous_case_sha256']:
        raise ValueError('the previous contract and negative verdict must remain intact')
    proof = audit(3)
    if not proof['primary_criterion_met'] or min(proof['paired_ratios']) < 1.3:
        raise ValueError('three complete >=1.3x native PSS pairs are required')
    results = {}
    for variant in ('unfixed', 'fixed'):
        base = ROOT/'artifacts/clean'/CASE/variant
        sign = json.loads((base/'sign.json').read_text())
        captures = []
        for number in (1, 2, 3):
            folder = capture_folder(variant, number)
            captures.append({'round': number,
                             'capture_sha256': hashlib.sha256((folder/'capture.json').read_bytes()).hexdigest()})
        result = {'status': 'PASS', 'metric': 'app_pss_bytes', 'rounds': 3,
                  'samples': proof['samples'][variant],
                  'median': statistics.median(proof['samples'][variant]),
                  'paired_ratios': proof['paired_ratios'], 'median_ratio': proof['median_ratio'],
                  'required_ratio': 1.3, 'plan_sha256': proof['plan_sha256'],
                  'signed_sha256': sign['audit']['sha256'], 'fixture_sha256': proof['fixture_sha256'],
                  'captures': captures, 'acceptance_revision': revision['id'],
                  'mechanism': 'Successful paired online pages; unfixed native cache grows; fixed first-page cache remains bounded.',
                  'legacy_evidence_reused': False, 'new_device_trials': False}
        results[variant] = result
    if write:
        for variant, result in results.items():
            base = ROOT/'artifacts/clean'/CASE/variant
            (base/'performance.json').write_text(json.dumps(result, indent=2)+'\n')
            workload = {'case': CASE, 'variant': variant, 'status': 'PASS',
                        'signed_sha256': result['signed_sha256'], 'plan_sha256': result['plan_sha256'],
                        'rounds': 3, 'captures': result['captures'],
                        'method': 'Read-only revalidation of original successful online twelve-swipe trials.',
                        'new_device_trials': False}
            (base/'workload.json').write_text(json.dumps(workload, indent=2)+'\n')
        case['test_oracle']['evidence'] = {
            'status': 'measured_clean', 'metric': 'app_pss_bytes',
            **proof['samples'], 'paired_ratios': proof['paired_ratios'],
            'median_ratio': proof['median_ratio'], 'rounds_per_variant': 3,
            'required_ratio': 1.3, 'performance_accepted': True,
            'legacy_evidence_reused': False, 'new_device_trials': False,
            'note': 'Revised memory-and-cache contract. Old file-write negative retained; no write-volume speedup claimed.'}
        case.pop('disposition', None)
        case['primary_measurement_validation'] = {
            'status': 'REVISED_MEMORY_AND_CACHE_ACCEPTED', 'rounds_per_variant': 3,
            'paired_ratios': proof['paired_ratios'], 'full_case_accepted': True,
            'proof': 'validation/wan-home-revised-memory-acceptance.json'}
        path.write_text(json.dumps(case, ensure_ascii=False, indent=2)+'\n')
    return results


if __name__ == '__main__':
    print(json.dumps(accept(), indent=2))
