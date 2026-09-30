from pathlib import Path
import json,subprocess,os,shutil
from concurrent.futures import ThreadPoolExecutor
B=Path(__file__).resolve().parent
assert len(list((B/'results').glob('*/C*/status.json')))==39, 'Wait for blind outputs'
env=os.environ.copy();env['HAPRAY_WORKSPACE']=str(B);env['HAPRAY_ROOT_CAUSE_EXECUTION']='agent'
for k in ['LLM_API_KEY','HAPRAY_ROOT_CAUSE_AGENT_CMD','HAPRAY_SYMBOL_RECOVERY_AGENT_CMD']:env.pop(k,None)
def render(p):
    r=p.parent;case=r.name;root=B/'blind'/case
    report=root/(root/'HAPRAY_REPORT_PATH.txt').read_text().strip()
    shutil.copyfile(p,r/'root_cause_agent_result.json')
    cmd=[str(B/'hapray-release/runtime/tools/perf-testing/perf-testing.exe'),'root-cause','--report-dir',str(report),'--source-dir',str(root/'source'),'--output',str(r/'root_cause.md')]
    with (r/'hapray-render.log').open('w',encoding='utf-8') as f:
        result=subprocess.run(cmd,cwd=B,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
    (r/'hapray-render-status.json').write_text(json.dumps({'exit_code':result.returncode,'report_exists':(r/'root_cause.md').exists()}))
    print(r.parent.name,case,result.returncode,flush=True)
with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(render,sorted((B/'results').glob('*/C*/prediction.json'))))
