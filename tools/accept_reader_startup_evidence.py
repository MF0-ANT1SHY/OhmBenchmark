#!/usr/bin/env python3
"""Accept complete startup refresh latency, with native diagnostics and no app probes."""
import hashlib
import json
from pathlib import Path
import statistics
from measurement_paths import capture_root
from reader_data_fixture import verify_preparation
from reader_refresh_latency import verify_capture as verify_latency
from rss_service_fixture import same_instance
from scheduler_cpu import compute, window_from_markers

ROOT = Path(__file__).resolve().parents[1]
CASE = 'sheafreader_refresh_feeds_sequential'
METRIC = 'startup_refresh_elapsed_s'
COMPARISON = 'unfixed conservative lower bound >= 1.5 * fixed upper bound over 3 paired rounds'


def verify_native_capture(receipt, trace):
    if receipt.get('status') != 'CAPTURED' or receipt.get('configuration_cleanup_error'):
        raise ValueError('native capture or cleanup failed')
    before, after = receipt['process_before'], receipt['process_after']
    if (before != after or receipt['pids'] != [before['pid']] or before['start_ticks'] <= 0
            or before['command'].split('\0', 1)[0].strip() != 'com.sheafreader.hm'):
        raise ValueError('startup process identity changed')
    if (receipt['online_cpus_before'] != receipt['online_cpus_after']
            or receipt['clock_before'] != receipt['clock_after'] or '[boot]' not in receipt['clock_before']
            or receipt['buffer_size_kb_before'] != receipt['buffer_size_kb_after']):
        raise ValueError('native tracing conditions changed or cleanup failed')
    latency = receipt['startup_latency']
    if (latency['start'] != receipt['action_start_monotonic'] or latency['end'] != receipt['action_end_monotonic']
            or latency['pid_before'] != str(before['pid'])):
        raise ValueError('latency and trace refer to different actions or processes')
    bounds = verify_latency(latency, 1.5)
    if bounds != receipt['latency_bounds']:
        raise ValueError('latency summary differs from native observations')
    start, end = window_from_markers(trace, receipt['marker_token'], receipt['pids'])
    raw = compute(trace, receipt['pids'], start, end, receipt['online_cpus_before'])
    if raw != receipt['scheduler_cpu']:
        raise ValueError('diagnostic CPU summary differs from native scheduling')
    if (end-start)/1e9 < bounds['elapsed_upper_s']:
        raise ValueError('native diagnostic window does not enclose the complete action')
    return bounds, raw


def accept(cid, write=True, require_pass=True):
    if cid != CASE:
        raise ValueError('startup refresh acceptance targets a different case')
    path = ROOT/'cases'/cid/'case.json';case = json.loads(path.read_text())
    if case['test_oracle']['metric'] != METRIC or case['test_oracle']['comparison'] != COMPARISON:
        raise ValueError('unsupported startup latency contract')
    plan_hash = hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest()
    variants = {};fixtures = set();service = None
    for variant in ('unfixed', 'fixed'):
        folder = ROOT/'artifacts/clean'/cid/variant
        sign = json.loads((folder/'sign.json').read_text())
        workload = json.loads((folder/'workload.json').read_text())
        first_path = capture_root(folder, case, METRIC)/'round-1/capture.json'
        if (workload.get('status') != 'PASS' or workload.get('plan_sha256') != plan_hash
                or workload.get('signed_sha256') != sign['audit']['sha256']
                or workload.get('native_capture_sha256') != hashlib.sha256(first_path.read_bytes()).hexdigest()):
            raise ValueError('ordinary startup workload is not bound to the first native trial')
        samples = [];lowers = [];captures = []
        for number in (1, 2, 3):
            directory = capture_root(folder, case, METRIC)/f'round-{number}'
            record_path = directory/'capture.json';r = json.loads(record_path.read_text())
            if (r['case'] != cid or r['variant'] != variant or r['round'] != number
                    or r['measurement_revision'] != case['measurement_revision']
                    or r['signed_sha256'] != sign['audit']['sha256'] or r['plan_sha256'] != plan_hash):
                raise ValueError('startup capture provenance mismatch')
            first, last = r['reader_fixture_before'], r['reader_fixture_after']
            verify_preparation(first, last)
            if first['sha256'] != r['fixture_sha256'] or first['service'].get('network_delay_s') != 1.5:
                raise ValueError('input or declared RSS delay mismatch')
            if service is None:service = first['service']
            same_instance(service, first['service'])
            fixtures.add(r['fixture_sha256'])
            bounds, cpu = verify_native_capture(r, directory/'trace.htrace')
            samples.append(bounds['elapsed_upper_s']);lowers.append(bounds['elapsed_lower_s'])
            captures.append({'round': number, 'capture_sha256': hashlib.sha256(record_path.read_bytes()).hexdigest(),
                             'trace_sha256': cpu['trace_sha256'], 'app_cpu_ms': cpu['app_cpu_ms'],
                             'remote_artifacts': r['remote_artifacts']})
        variants[variant] = {'samples': samples, 'lower_bounds': lowers, 'captures': captures,
                             'signed_sha256': sign['audit']['sha256']}
    if len(fixtures) != 1:
        raise ValueError('all six captures must use identical ordinary contents')
    ratios = [u/f for u,f in zip(variants['unfixed']['lower_bounds'], variants['fixed']['samples'])]
    nominal = [u/f for u,f in zip(variants['unfixed']['samples'], variants['fixed']['samples'])]
    median = statistics.median(variants['unfixed']['lower_bounds'])/statistics.median(variants['fixed']['samples'])
    passed = min(ratios) >= 1.5 and median >= 1.5
    results = {}
    for variant, data in variants.items():
        results[variant] = dict(data, status='PASS' if passed else 'FAIL', metric=METRIC, rounds=3,
                               median=statistics.median(data['samples']), paired_ratios=ratios, median_ratio=median,
                               nominal_paired_ratios=nominal, plan_sha256=plan_hash,
                               fixture_sha256=next(iter(fixtures)), legacy_evidence_reused=False,
                               method='Complete app startup and all-feed refresh; conservative timing bounds under declared 1.5-second RSS response latency. Native CPU data is diagnostic, not an improvement claim.')
        if write:
            (ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(results[variant], indent=2)+'\n')
    if write:
        case['test_oracle']['evidence'] = {'status': 'measured_clean' if passed else 'measured_clean_failed',
            'metric': METRIC, 'unfixed': results['unfixed']['samples'], 'fixed': results['fixed']['samples'],
            'paired_conservative_ratios': ratios, 'median_ratio': median, 'rounds_per_variant': 3,
            'legacy_evidence_reused': False, 'note': results['unfixed']['method']}
        path.write_text(json.dumps(case, ensure_ascii=False, indent=2)+'\n')
    if not passed and require_pass:
        raise ValueError(f'conservative latency improvement below 1.5x: {ratios}')
    return results
