"""Count observed native RDB events inside the same measured trace spans."""
import gzip,json,pathlib,re,collections
root=pathlib.Path(__file__).resolve().parents[1]; results=[]
line_re=re.compile(r'\s*(.+)-(\d+)\s+\(\s*(\d+|-----)\)\s+\[(\d+)\].*?\s(\d+\.\d+):\s+(\w+):\s+(.*)')
for row in json.loads((root/'measurements/summary.json').read_text()):
    if row['case'] not in ['browser_insert_date_lookup_cache','sheafreader_unread_counts_n_plus_1','browser_eager_history_load','browser_history_delete_no_transaction']:continue
    events=[];start=end=None
    with gzip.open(root/row['path']/'trace.txt.gz','rt',errors='replace') as f:
        for line in f:
            if 'tracing_mark_write:' not in line:continue
            m=line_re.match(line)
            if not m:continue
            name,tid,tgid,cpu,ts,event,payload=m.groups();ts=float(ts)
            if tgid!=str(row['pid']):continue
            if 'OHMB/'+row['case'] in payload:
                if payload.startswith('S|'):start=ts
                if payload.startswith('F|'):end=ts
            if payload.startswith('B|') and '|I36' in payload:events.append((ts,payload.split('|',2)[-1]))
    counts=collections.Counter(name for ts,name in events if start is not None and end is not None and start<=ts<=end)
    results.append(dict(case=row['case'],variant=row['variant'],run=row['run'],native_rdb_trace_events=dict(counts)))
(root/'measurements/native-rdb-events.json').write_text(json.dumps(results,indent=2))
for row in results:print(row)
