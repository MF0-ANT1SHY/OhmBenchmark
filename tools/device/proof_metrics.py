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


MEASURES = {
    'browser_eager_history_load': m_eager,
    'browser_history_list_foreach': m_list,
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
        ok = (ru and ru >= 30 and (rf == 0)
              and qu and qf == 0 and cu and cf and cu > cf * 1.2)
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'startup_cpu_ms': [cu, cf], 'cpu_gap': gap,
                             'rows_at_startup': [ru, rf], 'startup_queries': [qu, qf]}}

    if case == 'browser_history_list_foreach':
        bu, bf = med('rows_built_at_open', unfixed), med('rows_built_at_open', fixed)
        ok = bu and bf is not None and bu >= 60 and bf <= 30 and bu > bf * 2
        return {'verdict': 'PASS' if ok else 'FAIL',
                'evidence': {'rows_built_at_open': [bu, bf]}}

    # generic fallback: CPU medians, honest data-only verdict
    cu, cf = med('cpu_ms', unfixed), med('cpu_ms', fixed)
    return {'verdict': 'DATA_ONLY',
            'evidence': {'cpu_ms': [cu, cf]}, 'blocker': 'no oracle judge for case'}

# cases judged DATA_ONLY must be replaced by real judges as each case is
# brought up; see cases/<id>/case.json test_oracle.
