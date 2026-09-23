#!/usr/bin/env python3
"""Compare unfixed vs fixed trace/hilog artifacts per executed case and judge
whether the injected performance bug is actually visible in the data.

Usage: python3 analyze_campaign.py [case_id ...]   (default: all EXECUTABLE)
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import analyze  # noqa: E402

RESULTS = os.path.join(REPO, 'results')
APP_COMM = 'myapplication2'


def rep_files(case_dir, rep):
    tr = sorted(glob.glob(os.path.join(case_dir, f'*_{rep}_*.chtrace')))
    hl = sorted(glob.glob(os.path.join(case_dir, f'*_{rep}_*.hilog')))
    return tr, hl


def app_pid(trace):
    counts = {}
    with analyze.open_trace(trace) as f:
        for line in f:
            m = re.search(rf'{APP_COMM}-(\d+)', line)
            if m:
                p = int(m.group(1))
                counts[p] = counts.get(p, 0) + 1
    return max(counts, key=counts.get) if counts else None


def count_creates(trace, pid, t0=None, t1=None):
    n = 0
    pat = re.compile(rf'B\|{pid}\|H:Create')
    with analyze.open_trace(trace) as f:
        for line in f:
            if pat.search(line):
                m = analyze.LINE.match(line)
                if not m:
                    continue
                ts = float(m.group('ts'))
                if (t0 and ts < t0) or (t1 and ts > t1):
                    continue
                n += 1
    return n


def hilog_count(hlog, needle, pid=None):
    n = 0
    for line in analyze._clean(hlog):
        if needle in line:
            if pid and f' {pid} ' not in line[:44]:
                continue
            n += 1
    return n


def cpu_during(trace, pid):
    t0 = analyze.pid_first_ts(trace, pid)
    if t0 is None:
        return None, None, None
    # window = app lifetime inside capture
    return analyze.cpu_time(trace, pid), t0, None


def hilog_marker_dt(hlog, pid, marker):
    return analyze.hilog_marker_dt(hlog, pid, marker)


def hilog_for(trace_path):
    """capture k pairs trace <case>_repN_k.chtrace with hilog repN_(k+1).hilog"""
    m = re.search(r'_rep(\d+)_(\d+)\.chtrace$', trace_path)
    if not m:
        return None
    return os.path.join(os.path.dirname(trace_path),
                        f'rep{m.group(1)}_{int(m.group(2)) + 1}.hilog')


def collect(case):
    out = {}
    camp = [json.loads(l) for l in open(os.path.join(RESULTS, 'campaign.jsonl'))]
    rec0 = next((r for r in camp if r['case'] == case), {})
    for variant in ('unfixed', 'fixed'):
        reps = []
        for tr in [r.get('trace') for r in rec0.get(f'reps_{variant}', [])]:
            trace = tr
            pid = app_pid(trace)
            if not pid:
                continue
            total, t_first, _ = cpu_during(trace, pid)
            rec = {
                'trace': os.path.basename(trace),
                'pid': pid,
                'cpu_ms': round(total or 0, 1),
                'creates': count_creates(trace, pid),
            }
            hlog = hilog_for(trace)
            if hlog and os.path.exists(hlog):
                rec['hilog'] = os.path.basename(hlog)
                rec['marker_startup_ms'] = hilog_marker_dt(hlog, pid, '项目已启动')
                rec['save_logs'] = hilog_count(hlog, '保存浏览记录', pid)
                rec['progress_logs'] = hilog_count(hlog, 'onProgressChange progress', pid)
                rec['title_logs'] = hilog_count(hlog, 'onTitleReceive title', pid)
                rec['loadmore_bytes'] = sum(len(l) for l in analyze._clean(hlog) if '<<<<<<' in l and f' {pid} ' in l[:44])
                rec['font_logs'] = hilog_count(hlog, 'registerFont', pid)
            reps.append(rec)
        out[variant] = reps
    return out


def judge(case, d):
    """Return (metric_description, unfixed_value, fixed_value, verdict)"""
    u = d['unfixed'][0] if d['unfixed'] else None
    f = d['fixed'][0] if d['fixed'] else None
    if not u or not f:
        return None

    def ratio(a, b):
        return round(a / b, 2) if b else None

    if case == 'browser_eager_history_load':
        mu, mf = u.get('marker_startup_ms'), f.get('marker_startup_ms')
        cu, cf = u['cpu_ms'], f['cpu_ms']
        return (f'startup cpu(un)={cu}ms cpu(fi)={cf}ms marker(un)={mu}ms marker(fi)={mf}ms',
                cu, cf, 'BUG SEEN' if cf and cu > cf * 1.15 else 'no clear gap')
    if case == 'browser_history_list_foreach':
        return (f'component builds scroll: un={u["creates"]} fi={f["creates"]}',
                u['creates'], f['creates'], 'BUG SEEN' if u['creates'] > f['creates'] * 1.3 else 'no clear gap')
    if case == 'browser_history_delete_no_transaction':
        return (f'app cpu in window: un={u["cpu_ms"]}ms fi={f["cpu_ms"]}ms',
                u['cpu_ms'], f['cpu_ms'], 'data only (no delete marker; window coarse)')
    if case == 'browser_insert_date_lookup_cache':
        return (f'saves un={u.get("save_logs")} fi={f.get("save_logs")}; cpu un={u["cpu_ms"]}ms fi={f["cpu_ms"]}ms',
                u['cpu_ms'], f['cpu_ms'], 'proxy (per-save SQL not in trace)')
    if case == 'sepweather_font_register_per_page':
        return (f'component builds: un={u["creates"]} fi={f["creates"]}; cpu un={u["cpu_ms"]} fi={f["cpu_ms"]}',
                u['creates'], f['creates'], 'proxy (MainPage recreation count unknown)')
    if case == 'wanharmony_web_progress_log_storm':
        pu, pf = u.get('progress_logs'), f.get('progress_logs')
        return (f'progress log lines: un={pu} fi={pf}',
                pu, pf, 'BUG SEEN' if pu and pf is not None and pu > pf * 2 else 'no clear gap')
    if case == 'wanharmony_html_decode_per_render':
        return (f'app cpu during scroll: un={u["cpu_ms"]}ms fi={f["cpu_ms"]}ms',
                u['cpu_ms'], f['cpu_ms'], 'BUG SEEN' if u['cpu_ms'] > f['cpu_ms'] * 1.15 else 'no clear gap')
    if case == 'wanharmony_persisted_home_list_growth':
        lu, lf = u.get('loadmore_bytes', 0), f.get('loadmore_bytes', 0)
        return (f'loadmore log bytes un={lu} fi={lf}; cpu un={u["cpu_ms"]} fi={f["cpu_ms"]}',
                lu, lf, 'proxy')
    if case == 'wanharmony_history_log_materialization':
        tu, tf = u.get('title_logs'), f.get('title_logs')
        return (f'title events un={tu} fi={tf}; cpu un={u["cpu_ms"]} fi={f["cpu_ms"]}',
                u['cpu_ms'], f['cpu_ms'], 'proxy')
    return ('generic', u['cpu_ms'], f['cpu_ms'], 'data only')


def main():
    cases = sys.argv[1:]
    if not cases:
        camp = [json.loads(l) for l in open(os.path.join(RESULTS, 'campaign.jsonl'))]
        seen = {}
        for r in camp:
            if r.get('verdict') == 'EXECUTABLE':
                seen[r['case']] = True
        cases = sorted(seen)
    print(f'{"case":44s} {"metric (unfixed vs fixed)":70s} verdict')
    proven = 0
    total = 0
    for case in cases:
        d = collect(case)
        if not d['unfixed'] or not d['fixed']:
            print(f'{case:44s} missing artifacts')
            continue
        total += 1
        desc, uv, fv, verdict = judge(case, d)
        if verdict.startswith('BUG SEEN'):
            proven += 1
        print(f'{case:44s} {desc:70s} {verdict}')
    print(f'\n{total} cases with paired data; {proven} show the perf gap directly; '
          f'{total - proven} have data but need stronger markers/more reps for proof')


if __name__ == '__main__':
    main()
