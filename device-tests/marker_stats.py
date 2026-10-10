import gzip,re,sys,statistics,pathlib
root=pathlib.Path('/mnt/c/Users/research/AppData/Local/Temp/wa-measure/measurements/interviewapp_response_log_full_stringify')
for variant in ('unfixed','fixed'):
    allms=[]
    print(f'=== {variant}')
    for r in range(1,4):
        f=root/variant/f'run{r}'/'trace.txt.gz'
        blob=gzip.open(f,'rt',errors='replace').read()
        starts={}; durs=[]
        for m in re.finditer(r'(\d+\.\d+): tracing_mark_write: ([SF])\|(\d+)\|H:OHMB/response_logging',blob):
            t,kind,pid=float(m.group(1)),m.group(2),m.group(3)
            if kind=='S': starts[pid]=t
            elif pid in starts: durs.append((t-starts.pop(pid))*1000)
        print(f'  run{r}: n={len(durs)} median={statistics.median(durs):.3f}ms mean={statistics.mean(durs):.3f}ms sum={sum(durs):.1f}ms')
        allms+=durs
    print(f'  ALL n={len(allms)} median={statistics.median(allms):.3f}ms')
