#!/usr/bin/env python3
"""Per-case oracle metric extraction + median judging for run_proof.py.

measure_all(case, artifacts, variant) -> list of per-rep metric dicts
judge(case, unfixed_metrics, fixed_metrics) -> dict(verdict=..., evidence=...)
"""
import os
import re
import statistics
import sys
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze  # noqa: E402

APP_COMM = 'myapplication2'


def _pid(trace):
    counts = {}
    with analyze.open_trace(trace) as f:
        for line in f:
            m = re.search(rf'{APP_COMM}-(\d+)', line)
            if m:
                p = int(m.group(1))
                counts[p] = counts.get(p, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _pid_from_hilog(hlog):
    """The app's pid from hilog header columns (some launch paths rename the
    traced comm, but the hilog tag always carries the bundle)."""
    pid = None
    for line in analyze._clean(hlog):
        if APP_COMM not in line:
            continue
        m = re.match(r'\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\s+(\d+)\s+\d+\s', line)
        if m:
            pid = int(m.group(1))
    return pid


def resolve_pid(art):
    """art['pid'] (post-trigger pidof) -> trace comm -> hilog tag column."""
    pid = art.get('pid')
    if pid:
        return pid
    pid = _pid(art['trace'])
    if pid:
        return pid
    return _pid_from_hilog(art.get('hilog') or '')


def _count(hlog, needle, pid=None):
    n = 0
    for line in analyze._clean(hlog):
        if needle in line and (not pid or f' {pid} ' in line[:44]):
            n += 1
    return n


# ---------------------------------------------------------------- measures

def m_eager(art):
    """browser_eager_history_load: startup CPU between process start and the
    completion of the eager load. The unfixed per-day queries are concurrent
    (not awaited) so 项目已启动 fires before the materialization lands; the
    oracle's 'last RDB query completion' anchor is the last 查询到记录 row
    line. Rows/queries counts are corroborating (hilog may drop lines)."""
    trace, hlog = art['trace'], art['hilog']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    first_wall, lines = _hilog_pid_lines(hlog, pid)
    started = [w for w, l in lines if '项目已启动' in l]
    rows = [w for w, l in lines if '查询到记录：' in l]
    queries = sum(1 for w, l in lines if 'ResultSet column names' in l)
    t_first = analyze.pid_first_ts(trace, pid)
    if t_first is None or first_wall is None:
        return {'error': 'no trace anchor'}
    end_wall = max(started + rows) if (started or rows) else None
    cpu = None
    if end_wall is not None:
        t_end = t_first + (end_wall - first_wall) / 1000.0 + 0.05
        cpu = analyze.cpu_time(trace, pid, t0=t_first, t1=t_end)
    return {
        'startup_cpu_ms': round(cpu, 1) if cpu is not None else None,
        'rows_at_startup': len(rows),
        'startup_queries': queries,
    }


def m_list(art):
    """browser_history_list_foreach: time from the history-button tap to the
    first history row rendering (host-side layout polls). Data load is
    identical across variants, so the delta is the plain-ForEach full build vs
    LazyForEach viewport build."""
    res = art.get('result') or {}
    return {'first_row_s': res.get('first_row_s')}


@lru_cache(maxsize=1)
def _trace_lines(trace):
    # A proof has six traces; retaining every decoded 200-500MB file can
    # exhaust memory before the fixed variant is judged.
    with analyze.open_trace(trace) as f:
        return f.readlines()


def m_generic_cpu(art):
    trace = art['trace']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    return {'cpu_ms': round(analyze.cpu_time(trace, pid) or 0, 1)}


def m_insert(art):
    """browser_insert_date_lookup_cache: per-save wall time from consecutive
    保存浏览记录成功 hilog lines + block I/O ops in the browse window."""
    trace, hlog = art['trace'], art['hilog']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    stamps = []
    first_line = None
    last_line = None
    for line in analyze._clean(hlog):
        if not re.match(r'^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}', line):
            continue
        if f' {pid} ' not in line[:44]:
            continue
        if first_line is None:
            first_line = line
        if '保存浏览记录成功' in line:
            stamps.append(analyze._wall_ms(line))
            last_line = line
    deltas = [round(b - a, 1) for a, b in zip(stamps, stamps[1:])]
    med_delta = round(statistics.median(deltas), 1) if deltas else None
    io_ops = None
    if first_line is not None and last_line is not None:
        t0 = analyze.pid_first_ts(trace, pid)
        t1 = t0 + (analyze._wall_ms(last_line) - analyze._wall_ms(first_line)) / 1000.0
        io_ops = 0
        for line in _trace_lines(trace):
            mt = analyze.LINE.match(line)
            if not mt:
                continue
            ts = float(mt.group('ts'))
            if t0 <= ts <= t1 and 'block_rq_issue' in line:
                io_ops += 1
    return {
        'saves': len(stamps),
        'median_save_delta_ms': med_delta,
        'block_io_in_window': io_ops,
        'cpu_ms': round(analyze.cpu_time(trace, pid) or 0, 1),
    }


def _hilog_pid_lines(hlog, pid):
    """Parsed [(wall_ms, line)] for hilog lines belonging to pid."""
    out = []
    first = None
    for line in analyze._clean(hlog):
        if not re.match(r'^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}', line):
            continue
        if f' {pid} ' not in line[:44]:
            continue
        w = analyze._wall_ms(line)
        if first is None:
            first = w
        out.append((w, line))
    return first, out


def _mono_pid_lines(hlog, pid):
    """Monotonic hilog timestamps use the same boot clock as hitrace."""
    out = []
    for line in analyze._clean(hlog):
        m = re.match(r'^\s*(\d+\.\d+)\s+(\d+)\s+\d+\s', line)
        if m and int(m.group(2)) == pid:
            out.append((float(m.group(1)), line))
    return out


def m_wan_history(art):
    """CPU in each onTitleReceive handler, bracketed by its own log lines.
    Monotonic hilog timestamps line up directly with hitrace's boot clock.
    Old wall-clock captures retain mechanism evidence but cannot yield this
    handler-specific CPU metric."""
    trace, hlog = art['trace'], art['hilog']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    mono = art.get('hilog_clock') == 'monotonic'
    lines = _mono_pid_lines(hlog, pid) if mono else _hilog_pid_lines(hlog, pid)[1]
    events = [w for w, l in lines if 'onTitleReceive title:' in l]
    hl_bytes = sum(len(l) for w, l in lines if 'historyList =' in l)
    spans = []
    start = None
    for ts, line in lines:
        if 'onTitleReceive title:' in line:
            start = ts
        elif start is not None and '更新后 historyList' in line:
            if ts >= start and ts - start < (0.1 if mono else 100):
                spans.append((start, ts))
            start = None
    handler_cpu = None
    handler_wall = None
    if mono and spans:
        cpu_samples = analyze.cpu_time_windows(trace, pid, spans)
        handler_cpu = round(statistics.mean(cpu_samples), 3)
        handler_wall = round(statistics.mean((b - a) * 1000 for a, b in spans), 3)
    sizes = [int(m.group(1)) for _, line in lines
             if (m := re.search(r'historyList\.size = (\d+)', line))]
    size_logs = sum(1 for w, l in lines if 'historyList.size =' in l)
    return {
        'title_events': len(events),
        'title_handler_cpu_ms': handler_cpu,
        'title_handler_wall_ms': handler_wall,
        'handler_samples': len(spans),
        'history_log_bytes': hl_bytes,
        'history_size_logs': size_logs,
        'history_entries': statistics.median(sizes) if sizes else None,
    }


def m_wan_html_decode(art):
    """wanharmony_html_decode_per_render: app CPU per article-list child
    created while loading more pages. H:CreateTaskMeasure is a layout pass,
    not an article item, so do not use its count as the denominator."""
    trace = art['trace']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    groups = {}
    pat = re.compile(rf'B\|{pid}\|H:ForEachNode::Update Id\[(\d+)\] '
                     r'preIds\[(\d+)\] newIds\[(\d+)\].*additionalChildComps\[(\d+)\]')
    for line in _trace_lines(trace):
        m = pat.search(line)
        if m:
            node, before, after, added = map(int, m.groups())
            g = groups.setdefault(node, {'total_items': 0, 'rendered_items': 0})
            g['total_items'] = max(g['total_items'], after)
            g['rendered_items'] += added
    main = max(groups.values(), key=lambda g: g['total_items'], default={})
    cpu = analyze.cpu_time_process(trace, pid) or 0
    rendered = main.get('rendered_items', 0)
    per_item = round(cpu / rendered, 2) if rendered else None
    pages = set()
    for line in analyze._clean(art['hilog']):
        if f' {pid} ' in line[:44]:
            m = re.search(r'/article/list/(\d+)/json', line)
            if m:
                pages.add(int(m.group(1)))
    return {'rendered_items': rendered, 'total_items': main.get('total_items'),
            'pages_loaded_in_capture': sorted(pages),
            'cpu_ms': round(cpu, 1), 'cpu_per_item_ms': per_item}


def m_wan_persisted(art):
    """Per-process write volume while appending pages 11-20 to the feed.
    Global block_rq_issue includes unrelated processes, so use /proc/PID/io
    snapshots taken after each observed loadMore event instead."""
    trace = art['trace']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    result = art.get('result') or {}
    samples = result.get('io_samples') or []
    if len(samples) < 2:
        return {'error': 'no per-process IO samples'}
    cycles = samples[-1]['page'] - samples[0]['page']
    if cycles <= 0:
        return {'error': 'no loadMore cycles'}
    physical = samples[-1]['write_bytes'] - samples[0]['write_bytes']
    logical = samples[-1]['wchar'] - samples[0]['wchar']
    physical_steps = [(b['write_bytes'] - a['write_bytes']) /
                      (b['page'] - a['page']) for a, b in zip(samples, samples[1:])
                      if b['page'] > a['page']]
    logical_steps = [(b['wchar'] - a['wchar']) /
                     (b['page'] - a['page']) for a, b in zip(samples, samples[1:])
                     if b['page'] > a['page']]
    total_items = 0
    pat = re.compile(rf'B\|{pid}\|H:ForEachNode::Update Id\[\d+\] '
                     r'preIds\[\d+\] newIds\[(\d+)\]')
    with analyze.open_trace(trace) as f:
        for line in f:
            m = pat.search(line)
            if m:
                total_items = max(total_items, int(m.group(1)))
    return {'loadmore_cycles': cycles, 'total_items': total_items,
            'process_write_bytes': physical, 'process_wchar': logical,
            'write_bytes_per_cycle': round(physical / cycles, 1),
            'early_write_bytes': round(statistics.mean(physical_steps[:3]), 1),
            'late_write_bytes': round(statistics.mean(physical_steps[-3:]), 1),
            'early_wchar': round(statistics.mean(logical_steps[:3]), 1),
            'late_wchar': round(statistics.mean(logical_steps[-3:]), 1),
            'rss_kb': result.get('rss_kb')}


def m_wan_progress(art):
    """wanharmony_web_progress_log_storm: progress-log lines per page-load set."""
    hlog = art['hilog']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    progress = sum(1 for l in analyze._clean(hlog)
                   if 'onProgressChange progress:' in l and f' {pid} ' in l[:44])
    return {'progress_logs': progress}


def _trace_span(trace, seconds):
    """Trace-time window covering the middle of the capture."""
    last = None
    first = None
    for line in _trace_lines(trace):
        mt = analyze.LINE.match(line)
        if mt:
            ts = float(mt.group('ts'))
            if first is None:
                first = ts
            last = ts
    if first is None or last is None:
        return None, None
    t1 = last - 3.0
    t0 = max(first, t1 - seconds)
    return t0, t1


def _block_bytes(trace, t0=None, t1=None, reads=False):
    total = 0
    write_re = re.compile(r'block_rq_issue: \S+ (\S+) (\d+) ')
    for line in _trace_lines(trace):
        if 'block_rq_issue' not in line:
            continue
        mt = analyze.LINE.match(line)
        if not mt:
            continue
        ts = float(mt.group('ts'))
        if (t0 and ts < t0) or (t1 and ts > t1):
            continue
        m = write_re.search(line)
        if not m:
            continue
        flags, size = m.group(1), int(m.group(2))
        is_read = flags.startswith('R')
        if reads == is_read:
            total += size
    return total


def m_sepweather(art):
    """MainPage return-to-first-render latency for the five measured trips.
    The route marker precedes page construction; the next MainPage update and
    app FlushRenderTask bound the first frame on this OS build."""
    trace = art['trace']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    routes, updates, frames = [], [], []
    prefix = f'B|{pid}|H:'
    for line in _trace_lines(trace):
        if prefix not in line:
            continue
        mt = analyze.LINE.match(line)
        if not mt:
            continue
        ts = float(mt.group('ts'))
        if ('Router Page from entry/src/main/ets/pages/LocationListPage '
                'to entry/src/main/ets/pages/MainPage' in line):
            routes.append(ts)
        elif 'CustomNodeUpdate name:MainPage' in line:
            updates.append(ts)
        elif 'FlushRenderTask' in line:
            frames.append(ts)
    latencies = []
    for t in routes:
        update = next((x for x in updates if t <= x < t + 0.5), None)
        frame = next((x for x in frames if update is not None and
                      update <= x < t + 0.5), None)
        if frame is not None:
            latencies.append(round((frame - t) * 1000, 3))
    return {'mainpage_build_ms': round(statistics.mean(latencies), 3)
            if latencies else None,
            'recreations': len(latencies), 'per_recreation_ms': latencies,
            'global_read_bytes': _block_bytes(trace, reads=True)}


def m_ytmusic(art):
    """ytmusic_current_playing_timeupdate: steady-playback window render
    passes (CustomNodeUpdate spans) + CPU; unfixed re-renders ~10x/s."""
    trace = art['trace']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    t0, t1 = _trace_span(trace, 40)
    if t0 is None:
        return {'error': 'empty trace'}
    updates = 0
    upd_re = re.compile(rf'U\|{pid}\|H:CustomNodeUpdate|B\|{pid}\|H:CustomNodeUpdate')
    for line in _trace_lines(trace):
        mt = analyze.LINE.match(line)
        if not mt:
            continue
        ts = float(mt.group('ts'))
        if t0 <= ts <= t1 and upd_re.search(line):
            updates += 1
    cpu = analyze.cpu_time(trace, pid, t0=t0, t1=t1) or 0
    return {'steady_updates': updates, 'steady_cpu_ms': round(cpu, 1)}


def _jingmo_stamps(hlog, pid, marker):
    out = []
    for line in analyze._clean(hlog):
        if marker not in line or f' {pid} ' not in line[:44]:
            continue
        m = re.match(r'(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})', line)
        if m:
            out.append((analyze._wall_ms(m.group(1)), line))
    return out


def m_jingmo_import(art):
    """jingmo_dataset_import_no_transaction / sync_page_reimport: per-row
    dispatch logs ('index = N', one per unbatched INSERT), dataset refetch
    logs, and block write volume in the import window."""
    trace, hlog = art['trace'], art['hilog']
    pid = resolve_pid(art)
    if not pid:
        return {'error': 'no pid'}
    first_wall, lines = _hilog_pid_lines(hlog, pid)
    idx = [w for w, l in lines if re.search(r'index = \d+', l)]
    size = [w for w, l in lines if 'classic poem dataset size:' in l]
    skip = [l for w, l in lines if 'dataset already imported' in l]
    t_first = analyze.pid_first_ts(trace, pid)
    block = None
    span = None
    if size and idx and t_first is not None and first_wall is not None:
        t0 = t_first + (min(size) - first_wall) / 1000.0
        t1 = t_first + (max(idx) - first_wall) / 1000.0 + 25.0
        span = round(max(idx) - min(size), 0)
        block = _block_bytes(trace, t0, t1)
    return {'row_dispatch_logs': len(idx),
            'dataset_fetch_logs': len(size),
            'skip_logs': len(skip),
            'import_span_ms': span,
            'block_write_bytes': block}


MEASURES = {
    'browser_eager_history_load': m_eager,
    'browser_history_list_foreach': m_list,
    'browser_insert_date_lookup_cache': m_insert,
    'wanharmony_history_log_materialization': m_wan_history,
    'wanharmony_html_decode_per_render': m_wan_html_decode,
    'wanharmony_persisted_home_list_growth': m_wan_persisted,
    'wanharmony_web_progress_log_storm': m_wan_progress,
    'sepweather_font_register_per_page': m_sepweather,
    'ytmusic_current_playing_timeupdate': m_ytmusic,
    'jingmo_dataset_import_no_transaction': m_jingmo_import,
    'jingmo_sync_page_reimport': m_jingmo_import,
}


def measure_all(case, artifacts, variant):
    fn = MEASURES.get(case, m_generic_cpu)
    out = []
    for a in artifacts:
        try:
            m = fn(a)
        except Exception as e:  # keep reps independent
            m = {'error': str(e)[-160:]}
        m['variant'] = variant
        m['rep'] = a.get('rep')
        out.append(m)
    return out


# ---------------------------------------------------------------- judging

def _median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def judge(case, unfixed, fixed):
    """Return verdict dict; PASS requires the test_oracle comparison on medians."""
    def med(key, data):
        return _median([r.get(key) for r in data])

    ev = {'unfixed': unfixed, 'fixed': fixed}

    if case == 'browser_eager_history_load':
        cu, cf = med('startup_cpu_ms', unfixed), med('startup_cpu_ms', fixed)
        ru, rf = med('rows_at_startup', unfixed), med('rows_at_startup', fixed)
        qu, qf = med('startup_queries', unfixed), med('startup_queries', fixed)
        gap = (cu / cf - 1) if (cu and cf) else None
        # decisive: startup CPU gap (trace-based). hilog row/query counts are
        # corroborating evidence (hilog flow control can drop lines).
        ok = (cu and cf and cu > cf * 1.2 and (qu or 0) >= 3 and qf == 0)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'startup_cpu_ms': [cu, cf], 'cpu_gap': gap,
                             'rows_at_startup': [ru, rf], 'startup_queries': [qu, qf]}}

    if case == 'browser_history_list_foreach':
        bu, bf = med('first_row_s', unfixed), med('first_row_s', fixed)
        gap = (bu / bf - 1) if (bu and bf) else None
        ok = (bu and bf and bu > bf * 1.3)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'first_row_s': [bu, bf], 'gap': gap}}

    if case == 'browser_insert_date_lookup_cache':
        du, df = med('median_save_delta_ms', unfixed), med('median_save_delta_ms', fixed)
        iu, ifx = med('block_io_in_window', unfixed), med('block_io_in_window', fixed)
        su = med('saves', unfixed)
        gap = (du / df - 1) if (du and df) else None
        ok = (su and su >= 15 and du and df and du > df * 1.1) or \
             (iu and ifx and iu > ifx * 1.15)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'median_save_delta_ms': [du, df], 'delta_gap': gap,
                             'block_io': [iu, ifx]}}

    if case == 'wanharmony_history_log_materialization':
        eu, ef = med('title_events', unfixed), med('title_events', fixed)
        cu, cf = med('title_handler_cpu_ms', unfixed), med('title_handler_cpu_ms', fixed)
        bu, bf = med('history_log_bytes', unfixed), med('history_log_bytes', fixed)
        su, sf = med('history_size_logs', unfixed), med('history_size_logs', fixed)
        hu, hf = med('handler_samples', unfixed), med('handler_samples', fixed)
        history_entries = med('history_entries', fixed)
        cpu_gap = (cu / cf - 1) if (cu is not None and cf) else None
        ok = (eu and ef and eu >= 10 and ef >= 10 and hu and hf
              and hu >= 10 and hf >= 10 and history_entries and history_entries >= 100
              and cu is not None and cf and cu > cf * 1.3
              and bu and bu >= 50000 and (bf or 0) < bu / 10)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'title_events': [eu, ef],
                             'history_log_bytes': [bu, bf],
                             'history_size_logs': [su, sf],
                             'handler_samples': [hu, hf],
                             'history_entries_fixed': history_entries,
                             'title_handler_cpu_ms': [cu, cf], 'cpu_gap': cpu_gap}}

    if case == 'wanharmony_html_decode_per_render':
        iu, ifx = med('cpu_per_item_ms', unfixed), med('cpu_per_item_ms', fixed)
        cu, cf = med('rendered_items', unfixed), med('rendered_items', fixed)
        tu, tf = med('total_items', unfixed), med('total_items', fixed)
        gap = (iu / ifx - 1) if (iu and ifx) else None
        ok = (iu and ifx and cu and cf and cu >= 20 and cf >= 20
              and tu and tf and tu >= 100 and tf >= 100 and iu > ifx * 1.15)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'cpu_per_item_ms': [iu, ifx], 'gap': gap,
                             'rendered_items': [cu, cf], 'total_items': [tu, tf],
                             'pages_loaded_in_capture':
                             [r.get('pages_loaded_in_capture') for r in unfixed + fixed]}}

    if case == 'wanharmony_persisted_home_list_growth':
        bu, bf = med('process_write_bytes', unfixed), med('process_write_bytes', fixed)
        wu, wf = med('process_wchar', unfixed), med('process_wchar', fixed)
        cu, cf = med('loadmore_cycles', unfixed), med('loadmore_cycles', fixed)
        iu, ifx = med('total_items', unfixed), med('total_items', fixed)
        early_u, late_u = med('early_wchar', unfixed), med('late_wchar', unfixed)
        ratio = (bu / bf) if (bu is not None and bf) else None
        ok = (bu is not None and bf is not None and bu > 0 and bu > bf * 3
              and cu and cf and cu >= 10 and cf >= 10
              and iu and ifx and iu >= 200 and ifx >= 200
              and early_u is not None and late_u is not None
              and late_u > early_u * 1.3)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'process_write_bytes': [bu, bf], 'ratio': ratio,
                             'process_wchar': [wu, wf],
                             'loadmore_cycles': [cu, cf], 'total_items': [iu, ifx],
                             'unfixed_wchar_early_late': [early_u, late_u],
                             'rss_kb': [med('rss_kb', unfixed), med('rss_kb', fixed)]}}

    if case == 'wanharmony_web_progress_log_storm':
        pu, pf = med('progress_logs', unfixed), med('progress_logs', fixed)
        ok = (pu and pf is not None and pu >= 50 and pu > pf * 2)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'progress_logs': [pu, pf]}}

    if case == 'sepweather_font_register_per_page':
        cu, cf = med('mainpage_build_ms', unfixed), med('mainpage_build_ms', fixed)
        nu, nf = med('recreations', unfixed), med('recreations', fixed)
        gap = (cu / cf - 1) if (cu and cf) else None
        ok = (cu and cf and nu and nf and nu >= 5 and nf >= 5 and cu > cf)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'mainpage_build_ms': [cu, cf], 'gap': gap,
                             'recreations': [nu, nf],
                             'global_read_bytes':
                             [med('global_read_bytes', unfixed),
                              med('global_read_bytes', fixed)]}}

    if case == 'jingmo_dataset_import_no_transaction':
        iu, ifx = med('row_dispatch_logs', unfixed), med('row_dispatch_logs', fixed)
        bu, bf = med('block_write_bytes', unfixed), med('block_write_bytes', fixed)
        spanu, spanf = med('import_span_ms', unfixed), med('import_span_ms', fixed)
        ratio = (spanu / spanf) if (spanu and spanf) else None
        ok = (iu and ifx == 0 and spanu and spanf and spanu > spanf * 3) or \
             (bu and bf and bu > bf * 3)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'row_dispatch_logs': [iu, ifx],
                             'import_span_ms': [spanu, spanf], 'span_ratio': ratio,
                             'block_write_bytes': [bu, bf]}}

    if case == 'jingmo_sync_page_reimport':
        iu, ifx = med('row_dispatch_logs', unfixed), med('row_dispatch_logs', fixed)
        fu, ff = med('dataset_fetch_logs', unfixed), med('dataset_fetch_logs', fixed)
        sf, st = med('skip_logs', unfixed), med('skip_logs', fixed)
        ok = (iu and iu >= 1000 and ifx == 0 and (ff or 0) >= 1)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'row_dispatch_logs': [iu, ifx],
                             'dataset_fetch_logs': [fu, ff],
                             'skip_logs': [sf, st]}}

    if case == 'ytmusic_current_playing_timeupdate':
        uu, uf = med('steady_updates', unfixed), med('steady_updates', fixed)
        cu, cf = med('steady_cpu_ms', unfixed), med('steady_cpu_ms', fixed)
        gap = (cu / cf - 1) if (cu and cf) else None
        # unfixed ~600 page updates/min vs fixed ~60; UI CPU follows
        ok = (uu and uf is not None and uu > uf * 2) and (cu and cf and cu > cf * 1.1)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'steady_updates': [uu, uf],
                             'steady_cpu_ms': [cu, cf], 'cpu_gap': gap}}

    # generic fallback: CPU medians, honest data-only verdict
    cu, cf = med('cpu_ms', unfixed), med('cpu_ms', fixed)
    return {'verdict': 'DATA_ONLY',
            'evidence': {'cpu_ms': [cu, cf]}, 'blocker': 'no oracle judge for case'}

# cases judged DATA_ONLY must be replaced by real judges as each case is
# brought up; see cases/<id>/case.json test_oracle.
