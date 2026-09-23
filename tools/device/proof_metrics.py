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
    completion of the eager load. The unfixed per-day queries are concurrent
    (not awaited) so 项目已启动 fires before the materialization lands; the
    oracle's 'last RDB query completion' anchor is the last 查询到记录 row
    line. Rows/queries counts are corroborating (hilog may drop lines)."""
    trace, hlog = art['trace'], art['hilog']
    pid = art.get('pid') or _pid(trace)
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
    first history row rendering. Data load is identical across variants, so
    the delta is the plain-ForEach full build vs LazyForEach viewport build."""
    hlog = art['hilog']
    pid = art.get('pid') or _pid(art['trace'])
    if not pid:
        return {'error': 'no pid'}
    first_row_ms = None
    for line in analyze._clean(hlog):
        m = re.search(r'OHB openHistory firstRowMs=(\d+)', line)
        if m:
            first_row_ms = int(m.group(1))
            break
    cpu = analyze.cpu_time(art['trace'], pid) or 0
    return {'first_row_ms': first_row_ms,
            'cpu_ms': round(cpu, 1)}


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
    """sepweather_font_register_per_page: CPU per MainPage recreation round-trip
    + TTF read bytes in window (unfixed re-registers fonts on every creation)."""
    trace = art['trace']
    pid = art.get('pid') or _pid(trace)
    if not pid:
        return {'error': 'no pid'}
    cpu = analyze.cpu_time(trace, pid) or 0
    read_bytes = _block_bytes(trace, reads=True)
    return {'cpu_per_round_ms': round(cpu / 10.0, 1),
            'cpu_ms': round(cpu, 1),
            'read_bytes': read_bytes}


def m_ytmusic(art):
    """ytmusic_current_playing_timeupdate: steady-playback window render
    passes (CustomNodeUpdate spans) + CPU; unfixed re-renders ~10x/s."""
    trace = art['trace']
    pid = art.get('pid') or _pid(trace)
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
        bu, bf = med('first_row_ms', unfixed), med('first_row_ms', fixed)
        gap = (bu / bf - 1) if (bu and bf) else None
        ok = (bu and bf and bu > bf * 1.3)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'first_row_ms': [bu, bf], 'gap': gap}}

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

    if case == 'sepweather_font_register_per_page':
        cu, cf = med('cpu_per_round_ms', unfixed), med('cpu_per_round_ms', fixed)
        ru, rf = med('read_bytes', unfixed), med('read_bytes', fixed)
        gap = (cu / cf - 1) if (cu and cf) else None
        # fixed approaches the no-font-work floor: less CPU per recreation and
        # no repeated TTF reads
        ok = (cu and cf and cu > cf * 1.1) or (ru and rf is not None and ru > rf * 2)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'cpu_per_round_ms': [cu, cf], 'cpu_gap': gap,
                             'read_bytes': [ru, rf]}}

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
