#!/usr/bin/env python3
"""Per-case oracle metric extraction + median judging for run_proof.py.

measure_all(case, artifacts, variant) -> list of per-rep metric dicts
judge(case, unfixed_metrics, fixed_metrics) -> dict(verdict=..., evidence=...)
"""
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze  # noqa: E402

APP_COMM = 'myapplication2'


def _pid(trace):
    counts = {}
    with open(trace, 'r', errors='replace') as f:
        for line in f:
            m = re.search(rf'{APP_COMM}-(\d+)', line)
            if m:
                p = int(m.group(1))
                counts[p] = counts.get(p, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _count(hlog, needle, pid=None):
    n = 0
    for line in analyze._clean(hlog):
        if needle in line and (not pid or f' {pid} ' in line[:44]):
            n += 1
    return n


# ---------------------------------------------------------------- measures

def m_eager(art):
    """browser_eager_history_load: startup CPU between process start and the
    项目已启动 marker, plus eager rows/queries observable in hilog."""
    trace, hlog = art['trace'], art['hilog']
    pid = art.get('pid') or _pid(trace)
    if not pid:
        return {'error': 'no pid'}
    cpu, dt = analyze.startup_cpu_ms(trace, hlog, pid, '项目已启动')
    return {
        'startup_cpu_ms': round(cpu, 1) if cpu is not None else None,
        'startup_wall_ms': round(dt, 1) if dt is not None else None,
        'rows_at_startup': _count(hlog, '查询到记录：', pid),
        'startup_queries': _count(hlog, 'ResultSet column names', pid),
    }


def m_list(art):
    """browser_history_list_foreach: row components built when the history
    dialog opens (For-all vs LazyForEach) + app CPU for the whole flow."""
    trace, hlog = art['trace'], art['hilog']
    pid = art.get('pid') or _pid(trace)
    if not pid:
        return {'error': 'no pid'}
    # build window: process start -> dialog open done (OHB openHistory marker)
    open_wall = None
    first_line = None
    for line in analyze._clean(hlog):
        if not re.match(r'^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}', line):
            continue
        if f' {pid} ' not in line[:44]:
            continue
        if first_line is None:
            first_line = line
        if 'OHB openHistory ok' in line:
            open_wall = line
            break
    creates = 0
    if first_line is not None and open_wall is not None:
        t0 = analyze.pid_first_ts(trace, pid)
        t1 = t0 + (analyze._wall_ms(open_wall) - analyze._wall_ms(first_line)) / 1000.0
        pat = re.compile(rf'B\|{pid}\|H:Create')
        for line in _trace_lines(trace):
            mt = analyze.LINE.match(line)
            if not mt or pat.search(line) is None:
                continue
            ts = float(mt.group('ts'))
            if t0 <= ts <= t1:
                creates += 1
    return {
        'rows_built_at_open': creates,
        'cpu_ms': round(analyze.cpu_time(trace, pid) or 0, 1),
    }


_TRACE_CACHE = {}


def _trace_lines(trace):
    if trace not in _TRACE_CACHE:
        with open(trace, 'r', errors='replace') as f:
            _TRACE_CACHE[trace] = f.readlines()
    return _TRACE_CACHE[trace]


def m_generic_cpu(art):
    trace = art['trace']
    pid = art.get('pid') or _pid(trace)
    if not pid:
        return {'error': 'no pid'}
    return {'cpu_ms': round(analyze.cpu_time(trace, pid) or 0, 1)}


def m_insert(art):
    """browser_insert_date_lookup_cache: per-save wall time from consecutive
    保存浏览记录成功 hilog lines + block I/O ops in the browse window."""
    trace, hlog = art['trace'], art['hilog']
    pid = art.get('pid') or _pid(trace)
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


def m_wan_history(art):
    """wanharmony_history_log_materialization: CPU per onTitleReceive event
    window + total historyList log bytes (unfixed JSON-stringifies the whole
    list twice per open, fixed logs only the size)."""
    trace, hlog = art['trace'], art['hilog']
    pid = art.get('pid') or _pid(trace)
    if not pid:
        return {'error': 'no pid'}
    first_wall, lines = _hilog_pid_lines(hlog, pid)
    events = [w for w, l in lines if 'onTitleReceive title:' in l]
    hl_bytes = sum(len(l) for w, l in lines if 'historyList =' in l)
    cpu = None
    t_first = analyze.pid_first_ts(trace, pid)
    if events and t_first is not None and first_wall is not None:
        per = []
        for w in events:
            t0 = t_first + (w - first_wall) / 1000.0
            c = analyze.cpu_time(trace, pid, t0=t0, t1=t0 + 2.5)
            if c is not None:
                per.append(c)
        cpu = round(sum(per) / len(per), 1) if per else None
    return {
        'title_events': len(events),
        'cpu_per_title_ms': cpu,
        'history_log_bytes': hl_bytes,
    }


def m_wan_html_decode(art):
    """wanharmony_html_decode_per_render: app CPU divided by item components
    created during the scroll window (plain ForEach re-decodes per build)."""
    trace = art['trace']
    pid = art.get('pid') or _pid(trace)
    if not pid:
        return {'error': 'no pid'}
    creates = 0
    pat = re.compile(rf'B\|{pid}\|H:Create')
    for line in _trace_lines(trace):
        mt = analyze.LINE.match(line)
        if mt and pat.search(line):
            creates += 1
    cpu = analyze.cpu_time(trace, pid) or 0
    per_item = round(cpu / creates, 2) if creates else None
    return {'creates': creates, 'cpu_ms': round(cpu, 1), 'cpu_per_item_ms': per_item}


def m_wan_persisted(art):
    """wanharmony_persisted_home_list_growth: block write bytes during the
    load-more scroll (unfixed rewrites the whole list per load-more)."""
    trace = art['trace']
    pid = art.get('pid') or _pid(trace)
    if not pid:
        return {'error': 'no pid'}
    write_re = re.compile(r'block_rq_issue: \S+ (W\S*) (\d+) ')
    total = 0
    for line in _trace_lines(trace):
        if 'block_rq_issue' in line:
            m = write_re.search(line)
            if m:
                total += int(m.group(2))
    return {'block_write_bytes': total,
            'cpu_ms': round(analyze.cpu_time(trace, pid) or 0, 1)}


def m_wan_progress(art):
    """wanharmony_web_progress_log_storm: progress-log lines per page-load set."""
    hlog = art['hilog']
    pid = art.get('pid') or _pid(art['trace'])
    if not pid:
        return {'error': 'no pid'}
    progress = sum(1 for l in analyze._clean(hlog)
                   if 'onProgressChange progress:' in l and f' {pid} ' in l[:44])
    return {'progress_logs': progress}


MEASURES = {
    'browser_eager_history_load': m_eager,
    'browser_history_list_foreach': m_list,
    'browser_insert_date_lookup_cache': m_insert,
    'wanharmony_history_log_materialization': m_wan_history,
    'wanharmony_html_decode_per_render': m_wan_html_decode,
    'wanharmony_persisted_home_list_growth': m_wan_persisted,
    'wanharmony_web_progress_log_storm': m_wan_progress,
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
        bu, bf = med('rows_built_at_open', unfixed), med('rows_built_at_open', fixed)
        ok = bu and bf is not None and bu >= 60 and bf <= 30 and bu > bf * 2
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'rows_built_at_open': [bu, bf]}}

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
        cu, cf = med('cpu_per_title_ms', unfixed), med('cpu_per_title_ms', fixed)
        bu, bf = med('history_log_bytes', unfixed), med('history_log_bytes', fixed)
        gap = (cu / cf - 1) if (cu is not None and cf) else None
        ok = (eu and ef and eu >= 5 and cu is not None and cf is not None
              and cu > cf * 1.3 and bu > bf * 3)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'title_events': [eu, ef],
                             'cpu_per_title_ms': [cu, cf], 'cpu_gap': gap,
                             'history_log_bytes': [bu, bf]}}

    if case == 'wanharmony_html_decode_per_render':
        iu, ifx = med('cpu_per_item_ms', unfixed), med('cpu_per_item_ms', fixed)
        cu, cf = med('creates', unfixed), med('creates', fixed)
        gap = (iu / ifx - 1) if (iu and ifx) else None
        ok = (iu and ifx and cu and cf and cu >= 10 and iu > ifx * 1.15)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'cpu_per_item_ms': [iu, ifx], 'gap': gap,
                             'creates': [cu, cf]}}

    if case == 'wanharmony_persisted_home_list_growth':
        bu, bf = med('block_write_bytes', unfixed), med('block_write_bytes', fixed)
        ratio = (bu / bf) if (bu and bf) else None
        ok = (bu and bf and bu > bf * 3)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'block_write_bytes': [bu, bf], 'ratio': ratio}}

    if case == 'wanharmony_web_progress_log_storm':
        pu, pf = med('progress_logs', unfixed), med('progress_logs', fixed)
        ok = (pu and pf is not None and pu >= 50 and pu > pf * 2)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'progress_logs': [pu, pf]}}

    # generic fallback: CPU medians, honest data-only verdict
    cu, cf = med('cpu_ms', unfixed), med('cpu_ms', fixed)
    return {'verdict': 'DATA_ONLY',
            'evidence': {'cpu_ms': [cu, cf]}, 'blocker': 'no oracle judge for case'}

# cases judged DATA_ONLY must be replaced by real judges as each case is
# brought up; see cases/<id>/case.json test_oracle.
