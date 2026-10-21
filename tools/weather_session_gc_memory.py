"""Validate GC-request-conditioned diagnostic evidence, not GC completion."""
import math
import re

from system_pss import verify_window
from weather_session_memory import BUNDLE, growth_bounds, verify_extra, verify_requests
from weather_icon_pixels import icon_boxes


def verify_gc_receipts(record):
    """Bind two successful native requests and fixed waits to kernel boundaries."""
    baseline, post = record['baseline_samples'], record['post_samples']
    window = record['snapshots']
    if len(baseline) != 3 or len(post) != 3 or not window:
        raise ValueError('three kernel samples per boundary are required')
    if window[0] != baseline[-1] or window[-1] != post[-1]:
        raise ValueError('GC boundaries differ from measured window')
    pid, ticks = window[0]['pid'], window[0]['process_start_ticks']
    previous = 0
    for sample in [*baseline, *window[1:-1], *post]:
        verify_extra(sample, pid, ticks)
        if sample['read_start_monotonic'] < previous:
            raise ValueError('kernel observations overlap')
        previous = sample['monotonic']
    requests = record.get('gc_requests', [])
    if len(requests) != 2:
        raise ValueError('two native GC request receipts are required')
    for receipt, phase, samples in zip(requests, ('before', 'after'), (baseline, post)):
        if receipt['phase'] != phase or receipt['pid'] != pid:
            raise ValueError('GC request targets another phase or process')
        if receipt['command'] != f'hidumper --mem-jsheap {pid} --gc':
            raise ValueError('unexpected native GC command')
        match = re.search(r'__WEATHER_GC_EXIT__=(\d+)\s*$', receipt['raw_output'])
        if receipt['native_exit_code'] != 0 or not match or int(match[1]) != 0:
            raise ValueError('native GC command did not return success')
        start, end, settled = [receipt[k] for k in
                               ('start_monotonic', 'end_monotonic', 'settle_end_monotonic')]
        if not all(math.isfinite(x) for x in (start, end, settled)):
            raise ValueError('nonfinite GC timing')
        if not 0 < start <= end or receipt['settle_seconds'] != 10 or settled - end < 10:
            raise ValueError('fixed ten-second native GC settling interval missing')
        if settled > samples[0]['read_start_monotonic']:
            raise ValueError('kernel samples precede GC settling')
        if any(s['phase'] != phase for s in samples):
            raise ValueError('kernel boundary phase differs')
    if baseline[-1]['monotonic'] > record['action_start_monotonic']:
        raise ValueError('baseline overlaps measured work')
    if requests[1]['start_monotonic'] < record['action_end_monotonic']:
        raise ValueError('post-work GC request overlaps measured work')
    return growth_bounds([s['pss_bytes'] for s in baseline], [s['pss_bytes'] for s in post])


def verify_diagnostic(record):
    if (record.get('status') != 'CAPTURED' or record.get('performance_accepted') is not False
            or record.get('gc_completion_claimed') is not False):
        raise ValueError('diagnostic must not claim acceptance or GC completion')
    count = record['measured_returns']
    if type(count) is not int or count <= 0 or record['warmup_count'] != 10:
        raise ValueError('invalid ordinary workload count')
    verify_window(record, BUNDLE)
    bounds = verify_gc_receipts(record)
    if bounds != record['growth_bounds']:
        raise ValueError('growth differs from raw kernel totals')
    verify_requests(record, count)
    if len(record['steps']) != count:
        raise ValueError('incomplete ordinary workload')
    for number, step in enumerate(record['steps'], 1):
        if step['number'] != number:
            raise ValueError('ordinary workload order differs')
        icon_boxes(step['layout'])
    icon_boxes(record['initial_layout'])
    icon_boxes(record['final_layout'])
    if record['fixture_before'] != record['fixture_after']:
        raise ValueError('service changed during diagnostic')
    return bounds
