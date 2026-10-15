#!/usr/bin/env python3
"""Recompute paired app CPU time from private, provenance-bound native traces."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from reader_data_fixture import verify_preparation
from rss_refresh_progress import verify_observation
from scheduler_cpu import compute, window_from_markers
from wan_history_progress import verify_observation as verify_wan_observation, BUNDLE as WAN_BUNDLE
from install_wanharmony_history_fixture import verify_preparation as verify_wan_preparation

ROOT = Path(__file__).resolve().parents[1]
CASE = 'sheafreader_refresh_feeds_sequential'
WAN_CASE = 'wanharmony_history_log_materialization'


def verify_capture(receipt, trace):
    cid = receipt.get('case', CASE)
    if cid not in (CASE, WAN_CASE):
        raise ValueError('unsupported native trace case')
    bundle = 'com.sheafreader.hm' if cid == CASE else WAN_BUNDLE
    if receipt['status'] != 'CAPTURED' or receipt.get('configuration_cleanup_error'):
        raise ValueError('native recording or configuration cleanup failed')
    before, after = receipt['process_before'], receipt['process_after']
    if (before != after or receipt['pids'] != [before['pid']]
            or before['command'].split('\x00', 1)[0].strip() != bundle
            or type(before['start_ticks']) is not int or before['start_ticks'] <= 0):
        raise ValueError('native process identity changed or belongs to another app')
    if (receipt['online_cpus_before'] != receipt['online_cpus_after']
            or receipt['clock_before'] != receipt['clock_after']
            or '[boot]' not in receipt['clock_before']
            or receipt['buffer_size_kb_before'] != receipt['buffer_size_kb_after']):
        raise ValueError('native trace environment changed or was not restored')
    progress = receipt['reader_refresh' if cid == CASE else 'wan_history']
    (verify_observation if cid == CASE else verify_wan_observation)(progress)
    if cid == WAN_CASE and (progress['before']['pid'] != before['pid']
                           or progress['before']['start_ticks'] != before['start_ticks']):
        raise ValueError('web callbacks belong to a different native process')
    start, end = receipt['action_start_monotonic'], receipt['action_end_monotonic']
    if (not 0 < start < end or progress['before']['ended_monotonic'] > start
            or progress['after']['started_monotonic'] < start
            or progress['after']['ended_monotonic'] > end):
        raise ValueError('normal complete refresh was not observed inside the measured window')
    if cid == WAN_CASE and any(not start <= state['started_monotonic'] <= state['ended_monotonic'] <= end
                               for state in progress.get('during', [])):
        raise ValueError('native page snapshots were not observed inside the measured window')
    started, ended = window_from_markers(trace, receipt['marker_token'], receipt['pids'])
    raw = compute(trace, receipt['pids'], started, ended, receipt['online_cpus_before'])
    if raw != receipt['scheduler_cpu']:
        raise ValueError('app CPU receipt differs from raw native scheduling evidence')
    return raw


def accept(cid, write=True, require_pass=True, *, negative_screen=False):
    if negative_screen and (write or require_pass):
        raise ValueError('negative screening must be read-only and cannot accept performance')
    round_count = 1 if negative_screen else 3
    if cid not in (CASE, WAN_CASE):
        raise ValueError('native trace acceptance is not implemented for this case')
    path = ROOT/'cases'/cid/'case.json'
    case = json.loads(path.read_text())
    if case['test_oracle']['metric'] != 'trace_cpu_ms':
        raise ValueError('scheduling CPU time cannot validate another metric')
    plan_hash = hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest()
    variants, fixtures = {}, set()
    for variant in ('unfixed', 'fixed'):
        folder = ROOT/'artifacts/clean'/cid/variant
        sign = json.loads((folder/'sign.json').read_text())
        workload = json.loads((folder/'workload.json').read_text())
        if (workload['status'] != 'PASS' or workload['plan_sha256'] != plan_hash
                or workload['signed_sha256'] != sign['audit']['sha256']):
            raise ValueError('matching ordinary UI workload is not proven')
        device = json.loads((folder/'workload-device.json').read_text())
        if cid == CASE:
            if verify_observation(device['reader_refresh']) != workload['reader_refresh']:
                raise ValueError('workload refresh summary differs from native data')
            verify_preparation(workload['fixture'], workload['fixture_after'])
        else:
            if verify_wan_observation(device['wan_history']) != workload['wan_history']:
                raise ValueError('workload web summary differs from native callback/history evidence')
            verify_wan_preparation(workload['fixture'], device['wan_history']['before'])
        values, captures = [], []
        for number in range(1, round_count+1):
            directory = folder/'trace-captures'/f'round-{number}'
            receipt = json.loads((directory/'capture.json').read_text())
            if (receipt['case'] != cid or receipt['variant'] != variant or receipt['round'] != number
                    or receipt['plan_sha256'] != plan_hash
                    or receipt['signed_sha256'] != sign['audit']['sha256']
                    or receipt['fixture_sha256'] != workload['fixture']['sha256']):
                raise ValueError('native trace provenance or input identity mismatch')
            preparation = receipt['reader_fixture_before' if cid == CASE else 'wan_history_fixture_before']
            if cid == CASE:
                verify_preparation(preparation, receipt['reader_fixture_after'])
            else:
                verify_wan_preparation(preparation, receipt['wan_history']['before'])
            if preparation['sha256'] != receipt['fixture_sha256']:
                raise ValueError('native trace fixture differs from the validated input')
            raw = verify_capture(receipt, directory/'trace.htrace')
            fixtures.add(receipt['fixture_sha256'])
            values.append(raw['app_cpu_ns'])
            captures.append({'round': number, 'trace_sha256': raw['trace_sha256'],
                             'capture_sha256': hashlib.sha256((directory/'capture.json').read_bytes()).hexdigest(),
                             'app_cpu_ns': raw['app_cpu_ns'], 'remote_artifacts': receipt['remote_artifacts']})
        variants[variant] = {'values_ns': values, 'captures': captures, 'signed_sha256': sign['audit']['sha256']}
    if len(fixtures) != 1:
        raise ValueError('identical ordinary inputs are not proven across all native captures')
    ratios = [u/f for u, f in zip(variants['unfixed']['values_ns'], variants['fixed']['values_ns'])]
    median_ratio = statistics.median(variants['unfixed']['values_ns'])/statistics.median(variants['fixed']['values_ns'])
    passed = min(ratios) >= 1.2 and median_ratio >= 1.2
    if negative_screen and passed:
        raise ValueError('first pair is not negative; three complete pairs are required for acceptance')
    results = {}
    for variant, data in variants.items():
        samples = [value/1000000 for value in data['values_ns']]
        result = {'status': 'PASS' if passed else 'FAIL', 'metric': 'trace_cpu_ms', 'rounds': round_count,
                  'samples': samples, 'median': statistics.median(samples),
                  'paired_ratios': ratios, 'median_ratio': median_ratio,
                  'plan_sha256': plan_hash, 'signed_sha256': data['signed_sha256'],
                  'fixture_sha256': next(iter(fixtures)), 'captures': data['captures'],
                  'method': 'app on-CPU sched_switch intervals clipped to native-clock external markers',
                  'legacy_evidence_reused': False}
        results[variant] = result
        if write:
            (ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(result, indent=2)+'\n')
    case['test_oracle']['evidence'] = {'status': 'measured_clean' if passed else 'measured_clean_failed',
        'metric': 'trace_cpu_ms', 'unfixed': results['unfixed']['samples'], 'fixed': results['fixed']['samples'],
        'median_ratio': median_ratio, 'rounds_per_variant': round_count, 'legacy_evidence_reused': False,
        'note': 'Native scheduling recomputed for every round; unchanged 1.2x paired and median criteria.'}
    if write:
        path.write_text(json.dumps(case, indent=2, ensure_ascii=False)+'\n')
    if not passed and require_pass:
        raise ValueError(f'native CPU performance criterion not met: {ratios}')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=[CASE, WAN_CASE])
    accept(parser.parse_args().case)
