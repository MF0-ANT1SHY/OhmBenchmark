import json,glob,os,re,statistics
from pathlib import Path

def stat_value(path,name):
    if not path.exists(): return None
    m=re.search(r'([\d,]+)\s+'+re.escape(name),path.read_text(errors='replace'))
    return int(m.group(1).replace(',','')) if m else None
def vmrss(path):
    if not path.exists(): return None
    m=re.search(r'VmRSS:\s+(\d+)\s+kB',path.read_text(errors='replace'))
    return int(m.group(1)) if m else None
med=lambda v:statistics.median(v) if v else None

for d in sorted(glob.glob('measurements-staging/*/')):
    cid=os.path.basename(d.rstrip('/'))
    try:
        c=json.load(open(f'cases/{cid}/case.json'))
        st=c['test_oracle']['evidence']['status']
        if st!='supporting': continue
    except Exception: continue
    print(f'=== {cid}')
    for variant in ('unfixed','fixed'):
        instr,task,drss,res=[],[],[],[]
        for run in sorted(Path(d,variant).glob('run*')):
            i=stat_value(run/'perf-stat.txt','hw-instructions')
            t=stat_value(run/'perf-stat.txt','sw-task-clock')
            b,a=vmrss(run/'before.txt'),vmrss(run/'after.txt')
            rj=run/'result.json'
            if i:instr.append(i)
            if t:task.append(t)
            if b is not None and a is not None:drss.append(a-b)
            if rj.exists():res.append(json.loads(rj.read_text()).get('result'))
        print(f'  {variant:<8} instr={instr} task={task} drss={drss} result={res}')
    u,f=None,None
    # quick medians from staged re-read
