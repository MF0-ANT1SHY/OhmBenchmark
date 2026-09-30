from pathlib import Path
import subprocess,os,json,concurrent.futures
B=Path(__file__).resolve().parent;exe=B/'hapray-release/runtime/tools/perf-testing/perf-testing.exe'
env=os.environ.copy();env['HAPRAY_WORKSPACE']=str(B);env['HAPRAY_ROOT_CAUSE_EXECUTION']='agent'
for k in ['LLM_API_KEY','HAPRAY_ROOT_CAUSE_AGENT_CMD','HAPRAY_SYMBOL_RECOVERY_AGENT_CMD']:env.pop(k,None)
mapping=json.loads((B/'private-map.json').read_text(encoding='utf-8'))
def run(item):
    a=item['id'];root=B/'blind'/a;raw=B/'raw'/a
    reports=list((root/'hapray').glob('*/report/summary.json'))
    if not reports:
        cmd=[str(exe),'update','--mode','1','--report_dir',str(root/'hapray'),'--perfs',*[str(raw/f'run{i}.data') for i in range(1,4)],'--traces',*[str(raw/f'run{i}.htrace') for i in range(1,4)],'--package-name',item['bundle'],'--pids',*map(str,item['pids']),'--app-name',a,'--scene','Recorded workload','--no-root-cause','--symbol-recovery-no-llm']
        with (B/'logs'/f'{a}-update.log').open('w',encoding='utf-8') as f:r=subprocess.run(cmd,cwd=B,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600)
        print(a,'update',r.returncode,flush=True)
        reports=list((root/'hapray').glob('*/report/summary.json'))
    if not reports:return
    report=reports[-1].parent
    cmd=[str(exe),'root-cause','--report-dir',str(report),'--source-dir',str(root/'source')]
    with (B/'logs'/f'{a}-root-cause.log').open('w',encoding='utf-8') as f:r=subprocess.run(cmd,cwd=B,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
    print(a,'root-cause',r.returncode,flush=True)
    # Remove benchmark identifiers from all model-visible text outputs, including runtime symbol paths.
    for p in (root/'hapray').rglob('*'):
        if p.suffix.lower() not in ['.json','.jsonl','.txt','.md','.log','.html']:continue
        s=p.read_text(encoding='utf-8',errors='replace')
        for i in mapping:s=s.replace(i['case'],'recorded_workload')
        p.write_text(s,encoding='utf-8')
    (root/'HAPRAY_REPORT_PATH.txt').write_text(str(report.relative_to(root)).replace('\\','/'),encoding='utf-8')
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for f in concurrent.futures.as_completed([pool.submit(run,i) for i in mapping]):
        try:f.result()
        except Exception as e:print(type(e).__name__,str(e)[:300],flush=True)
