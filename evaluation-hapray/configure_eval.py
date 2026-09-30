from pathlib import Path
import json,shutil,re
B=Path(__file__).resolve().parent
PY=r'C:\Users\30422\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
skill=B/'HapRay/skills/hapray'
for case in sorted((B/'blind').glob('C*')):
    target=case/'skill/hapray';shutil.copytree(skill,target,dirs_exist_ok=True)
    p=target/'SKILL.md';s=p.read_text(encoding='utf-8').replace('  description: |','description: |',1);p.write_text(s,encoding='utf-8')
    for harness in ['opencode','claude','dsh']:
        run=f'eval1-{harness}-{case.name}';r=B/'runs'/run;r.mkdir(parents=True,exist_ok=True)
        result=B/'results'/harness/case.name;result.mkdir(parents=True,exist_ok=True)
        where=r/('.agents/skills/hapray' if harness=='dsh' else '.claude/skills/hapray')
        shutil.copytree(target,where,dirs_exist_ok=True)
        args=[str(B/'blind_mcp.py'),str(case),str(result/'toolcalls.jsonl')]
        server={'command':PY,'args':args}
        if harness=='claude':
            (r/'mcp.json').write_text(json.dumps({'mcpServers':{'evidence':server}}),encoding='utf-8')
            (r/'settings.json').write_text(json.dumps({'permissions':{'allow':['mcp__evidence__*','Skill(hapray)'],'deny':['Bash','Read','Write','Edit','Glob','Grep','WebFetch','WebSearch','Agent']},'disableAllHooks':True}),encoding='utf-8')
        elif harness=='opencode':
            config={'$schema':'https://opencode.ai/config.json','model':'blind/deepseek-flash','provider':{'blind':{'npm':'@ai-sdk/openai-compatible','name':'DeepSeek budget proxy','options':{'baseURL':f'http://127.0.0.1:18780/{run}/v1','apiKey':'local-proxy'},'models':{'deepseek-flash':{'name':'deepseek-flash','limit':{'context':1000000,'output':8192},'reasoning':True}}}},'mcp':{'evidence':{'type':'local','command':[PY,*args],'enabled':True}},'permission':{'*':'deny','skill':{'hapray':'allow'},'evidence_*':'allow'},'share':'disabled','autoupdate':False}
            (r/'opencode.json').write_text(json.dumps(config),encoding='utf-8')
        else:
            default=(B/'dsh-default.yml').read_text(encoding='utf-8-sig')
            ids=re.findall(r'^- id: (.+)$',default,re.M)
            patch=[{'id':i,'disabled':True} for i in ids if (i.startswith('tool-') and i!='tool-skill') or i in ['agent-instructions','session-title-first-prompt-llm','llm-deepseek-account']]
            patch += [{'id':'llm-deepseek','config':{'baseURL':f'http://127.0.0.1:18780/{run}/anthropic','apiKeyEnv':'DEEPSEEK_API_KEY','thinking':'enabled','reasoningEffort':'high','maxTokens':8192}}, {'insert':[{'id':'blind-evidence','name':'@deepseek-ai/dsh-mcp-client','config':{'transport':'stdio','serverName':'evidence','command':PY,'args':args,'cwd':str(r),'failOnStartupError':True}}]}]
            (r/'patch.yml').write_text(json.dumps(patch),encoding='utf-8')
        prompt=f'''使用已配置的 hapray skill，独立分析匿名应用案例 {case.name} 的性能问题。这是已完成采集的只读分析任务，源代码和三轮同版本动态证据通过 evidence MCP 工具访问。先加载 hapray skill（如原生 Skill 不可用，读 skill/hapray/SKILL.md），再读 analysis/high-load-analysis.md 和 root-cause/comprehensive.md。
当前阶段为已有数据分析和 Agent 根因推断；不重新构建/采集/联网/询问路径。源码路径 source/；HAPRAY_REPORT_PATH.txt 指向已经由 HapRay CLI 生成的报告，其 root_cause_agent_task.json 是待完成的 Agent 任务。根据 skill，读取证据、必要时 SQL 查询 perf.db / trace.db，并结合原始源码补充定位。不要将 Pending Agent Inference 当检测结果。
阅读 workload.json 了解实际操作，但不要假设一定有 bug。最多报告 5 个与该操作相关、由源码或动态证据支持的性能问题，按把握排序；不要罗列无关的静态代码异味。没有足够证据可以返回空 suspects。仅凭函数名/耗时不能断言根因。当前采样事件为 sw-cpu-clock，不能把 event_count 解释为 CPU 指令数；缺失的 UI/内存事件应注明，不能杜撰。
你只能使用只读 evidence 工具读取本案例；工具内路径均相对匿名案例根目录。用户授权只读离线分析，因此跳过 skill 的路径询问、自动更新和 shell 步骤；本机 HapRay 已部署且已生成报告。本轮最多 14 次模型交互（含最终回答），请优先定位实际操作涉及的源码，再用动态证据检验机制；批量检索，最后给出结论。
最终只返回一个 JSON 数据对象（不加代码围栏），使用 HapRay Agent 结果格式：summary 字符串，suspects 数组。每项包含 rank, category（cpu-hotspot/empty-frame/frame-load/component-reuse/thread/ipc/so-load/memory）, owner, symbol, file, line_start, line_end, confidence（high/medium/low）, root_cause, fix, evidence（证据文本数组）。若有问题必须明确指出浪费工作的机制、具体函数/代码行以及对应证据。输出会由调用者保存并交回 HapRay，不需要写文件。'''
        (r/'prompt.txt').write_text(prompt,encoding='utf-8')
print('Configured 39 isolated harness runs with HapRay skill and read-only case tools')
