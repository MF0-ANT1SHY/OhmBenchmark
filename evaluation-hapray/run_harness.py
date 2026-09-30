from pathlib import Path
import os,subprocess,sys,time,json
B=Path(__file__).resolve().parent
NODE=r'C:\Users\30422\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
def run(harness,case,resume=False):
    name=f'eval1-{harness}-{case}';r=B/'runs'/name;out=B/'results'/harness/case
    env=os.environ.copy()
    for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:env.pop(key,None)
    env['NO_PROXY']='127.0.0.1,localhost';env['PYTHONIOENCODING']='utf-8'
    env['PATH']=str(Path(NODE).parent)+os.pathsep+env['PATH']
    env['HAPRAY_SKILL_AUTO_UPDATE']='0'
    if harness=='claude':
        env.update(ANTHROPIC_BASE_URL=f'http://127.0.0.1:18780/{name}/anthropic',ANTHROPIC_API_KEY='local-proxy',ANTHROPIC_AUTH_TOKEN='local-proxy',ANTHROPIC_MODEL='deepseek-flash',ANTHROPIC_DEFAULT_HAIKU_MODEL='deepseek-flash',CLAUDE_CONFIG_DIR=str(B/'homes'/name),CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',CLAUDE_CODE_GIT_BASH_PATH=r'C:\Program Files\Git\bin\bash.exe')
        cmd=[str(B/'harnesses/node_modules/@anthropic-ai/claude-code/bin/claude.exe'),'--bare','--model','deepseek-flash','--settings',str(r/'settings.json'),'--strict-mcp-config','--mcp-config',str(r/'mcp.json'),'--tools','Skill','--allowedTools','mcp__evidence__*','Skill(hapray)','--max-turns','24','--print','--output-format','stream-json','--verbose']
    elif harness=='opencode':
        env.update(OPENCODE_CONFIG_DIR=str(B/'homes'/name),OPENCODE_DISABLE_AUTOUPDATE='true',OPENCODE_DISABLE_DEFAULT_PLUGINS='true')
        cmd=[str(B/'harnesses/node_modules/opencode-windows-x64/bin/opencode.exe'),'run','--pure','--format','json','--model','blind/deepseek-flash']
    else:
        env.update(DSH_HOME=str(B/'homes'/name),DEEPSEEK_API_KEY='local-proxy',DEEPSEEK_BASE_URL=f'http://127.0.0.1:18780/{name}/anthropic')
        cmd=[NODE,str(B/'harnesses/node_modules/@deepseek-ai/dsh/lib/bin.js'),'--profile','headless','--patch',str(r/'patch.yml'),'--json','-']
    out.mkdir(parents=True,exist_ok=True);start=time.time()
    prompt=(r/'prompt.txt').read_text(encoding='utf-8')
    prefix=''
    if resume:
        events=[json.loads(l) for l in (out/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        if harness=='dsh':
            session=next(x['sessionId'] for x in events if x.get('type')=='session')
            cmd=cmd[:-1]+['--session-id',session,'-']
        elif harness=='opencode':
            session=next(x['sessionID'] for x in events if 'sessionID' in x)
            cmd+=['--session',session]
        else:raise ValueError('Resume unsupported')
        prompt='继续原有的匿名性能分析任务。上次因传输中断或最终 JSON 截断而未正常交付。不要引用其他运行、答案或新增假设。使用已有证据完成最终 JSON（summary/suspects），并简洁说明证据限制。'
        prefix='resume-'
    with (out/(prefix+'events.jsonl')).open('w',encoding='utf-8') as stdout,(out/(prefix+'stderr.txt')).open('w',encoding='utf-8') as stderr:
        try:
            result=subprocess.run(cmd,cwd=r,env=env,input=prompt,text=True,encoding='utf-8',stdout=stdout,stderr=stderr,timeout=1200)
            status={'exit_code':result.returncode,'elapsed_s':round(time.time()-start,1)}
        except subprocess.TimeoutExpired:status={'timeout':True,'elapsed_s':1200}
    (out/(prefix+'status.json')).write_text(json.dumps(status),encoding='utf-8');print(name,status,flush=True)
if __name__=='__main__':run(*sys.argv[1:3],resume=len(sys.argv)>3)
