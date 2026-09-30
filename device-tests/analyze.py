"""Summarize measured spans and on-CPU time from scheduler events, retaining all runs."""
import collections,csv,gzip,json,pathlib,re,statistics
root=pathlib.Path(__file__).resolve().parents[1]
rows=[]
line_re=re.compile(r'\s*(.+)-(\d+)\s+\(\s*(\d+|-----)\)\s+\[(\d+)\].*?\s(\d+\.\d+):\s+(\w+):\s+(.*)')
switch_re=re.compile(r'prev_pid=(\d+).*?next_pid=(\d+)')
for p in sorted((root/'measurements').glob('*/*/run*/result.json')):
    trace=p.parent/'trace.txt.gz'
    if not trace.exists():continue
    row=json.loads(p.read_text())
    pid=row['pid']; tids=set(); events=[]; start=end=None
    with gzip.open(trace,'rt',errors='replace') as f:
        for line in f:
            m=line_re.match(line)
            if not m:continue
            name,tid,tgid,cpu,ts,event,payload=m.groups(); ts=float(ts)
            if tgid==str(pid):tids.add(int(tid))
            if 'OHMB/'+row['case'] in payload:
                if payload.startswith('S|'):start=ts
                if payload.startswith('F|'):end=ts
            if event=='sched_switch':
                x=switch_re.search(payload)
                if x:events.append((ts,int(cpu),int(x[1]),int(x[2])))
    cpu_ms=0; main_ms=0; switches=0; running={}
    if start is not None and end is not None:
        for ts,cpu,prev,nxt in sorted(events):
            if cpu in running:
                last,task=running[cpu]
                dur=max(0,min(ts,end)-max(last,start))*1000
                if task in tids:cpu_ms+=dur
                if task==pid:main_ms+=dur
            if start<=ts<=end and prev in tids:switches+=1
            running[cpu]=(ts,nxt)
        row.update(trace_wall_ms=(end-start)*1000,trace_cpu_ms=cpu_ms,main_thread_cpu_ms=main_ms,trace_context_switches=switches)
    else:row['trace_error']='missing measurement boundary'
    for line in (p.parent/'perf-stat.txt').read_text().splitlines():
        m=re.match(r'\s*([\d,]+)\s+([\w-]+)',line)
        if m:row['perf_'+m[2]]=int(m[1].replace(',',''))
    row['path']=str(p.parent.relative_to(root)); rows.append(row)
(root/'measurements/summary.json').write_text(json.dumps(rows,indent=2))
for case in sorted({r['case'] for r in rows}):
    print(case)
    for variant in ['unfixed','fixed']:
        rs=[r for r in rows if r['case']==case and r['variant']==variant]
        print(' ',variant, 'wall_ms=',[round(r['elapsed_ms'],2) for r in rs], 'cpu_ms=',[round(r.get('trace_cpu_ms',-1),2) for r in rs])
