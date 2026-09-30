from pathlib import Path
import json,shutil,html,zipfile,datetime
B=Path(__file__).resolve().parent;O=B.parent.parent/'outputs/hapray-evaluation';O.mkdir(parents=True,exist_ok=True)
data=json.loads((B/'graded-results.json').read_text(encoding='utf-8'))
cost=json.loads((B/'cost-summary.json').read_text())
E=lambda x:html.escape(str(x))
labels={'hit':'命中','partial':'部分命中','miss':'漏检'}
for name in ['graded-results.json','protocol.json','blind-audit.json','cost-summary.json','dynamic-spotchecks.json','grading-criteria.json']:
    shutil.copyfile(B/name,O/name)
for r in data['rows']:
    src=B/'results'/r['harness']/r['id'];dst=O/'detections'/r['harness']/r['id'];dst.mkdir(parents=True,exist_ok=True)
    for name in ['prediction.json','root_cause.md','status.json','resume-status.json','serialization-repair.json','original-final.txt','hapray-render-status.json']:
        if (src/name).exists():shutil.copyfile(src/name,dst/name)
cards=''.join(f'<div class="card"><b>{E(h)}</b><strong>{v["hit"]}/13</strong><span>{v["partial"]} 部分命中 · {v["miss"]} 漏检</span></div>' for h,v in data['counts'].items())
table=''
for i in range(1,14):
    rows=[r for r in data['rows'] if r['id']==f'C{i:02d}'];c=rows[0]
    table+=f'<tr><td>{c["id"]}</td><td>{E(c["case"])}</td>'
    for r in rows:table+=f'<td class="{r["verdict"]}"><a href="#detail-{r["harness"]}-{r["id"]}">{labels[r["verdict"]]}</a>{" #"+str(r["matched_rank"]) if r["verdict"]=="hit" else ""}</td>'
    table+='</tr>'
details=''
for r in data['rows']:
    s=r['selected_prediction'] or {};prefix=f'detections/{r["harness"]}/{r["id"]}'
    details+=f'''<details id="detail-{r['harness']}-{r['id']}"><summary>{r['id']} · {r['harness']} · {labels[r['verdict']]}</summary>
<p><b>裁定：</b>{E(r['reason'])}</p><p><b>目标：</b>{E(r['target']['mechanism'])}</p>
<p><b>模型位置：</b>{E(s.get('file',''))}:{E(s.get('line_start',''))} {E(s.get('symbol',''))}</p>
<blockquote>{E(s.get('root_cause','未提出目标机制'))}</blockquote><p><b>动态支持：</b>{E(r['dynamic_support'])}</p><p><b>质量限制：</b>{E(r['quality_note'])}</p>
<p>原生首轮退出码 {r['initial_status'].get('exit_code')}；恢复交付 {r['resume']}；JSON 语法修复 {r['serialization_repair']}。</p>
<p><a href="{prefix}/prediction.json">完整原始判断 JSON</a> · <a href="{prefix}/root_cause.md">HapRay 生成的根因报告</a></p></details>'''
page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HapRay · 13 案例盲测</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;color:#18312f;background:#f4f7f5;max-width:1180px;margin:auto;padding:36px}}h1{{font-size:36px;line-height:1.2}}.cards{{display:flex;gap:16px;flex-wrap:wrap}}.card{{background:#fff;border:1px solid #d5dfd9;padding:20px;flex:1;min-width:180px}}strong{{display:block;font-size:36px;color:#16624b}}table{{border-collapse:collapse;width:100%;background:white;font-size:14px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}td:nth-child(2){{overflow-wrap:anywhere}}a{{color:#176751}}.partial,.partial a{{color:#a36800}}.miss,.miss a{{color:#ad3535}}details{{background:white;border:1px solid #d5dfd9;margin:12px 0;padding:16px}}summary{{cursor:pointer;font-weight:700}}blockquote{{margin:12px 0;padding:12px 20px;background:#f1f5f3;overflow-wrap:anywhere}}.note{{border-left:4px solid #bc842c;padding:12px 20px;background:#fff8e9}}small{{color:#596a63}}code{{overflow-wrap:anywhere}}</style>
<p>本地部署完成 · 39 次正式盲测 · DeepSeek Flash · 2026-10-01</p><h1>HapRay 能定位多数目标缺陷，<br>但解释仍需要审核。</h1>
<p>同一批 13 个案例，每个 harness 独立查看匿名未修复源码、操作说明及三轮实机 trace/perf。全部输出冻结后才对照 ground truth 人工评分。</p>
<div class="cards">{cards}<div class="card"><b>账户扣费增量</b><strong>¥{cost['account_decrease_cny']:.2f}</strong><span>预算 ¥50；含试跑及可能的账户其他使用</span></div></div>
<p class="note">“命中”仅指前五项内定位到目标机制和具体源码位置，不等于所有解释、数值与修复建议正确。DSH 13/13 不能解读为 100% 准确率；本轮没有负样本，也没有证明每个根因都由动态数据独立推出。</p>
<h2>逐案例结果</h2><p>点击状态查看裁定依据。C10 的 API 语义勘误见下文。</p><table><thead><tr><th>匿名编号</th><th>冻结后揭盲的案例</th><th>OpenCode</th><th>Claude Code</th><th>DSH</th></tr></thead><tbody>{table}</tbody></table>
<h2>评测边界</h2><p>部署版本：HapRay 1.5.9、OpenCode 1.18.33、Claude Code 2.1.286、DSH 0.2.0-rc.2。三种原生 harness 都加载 HapRay skill；模型统一 deepseek-flash，分析阶段 high thinking，每案例约 14 次模型交互预算。达到预算后仅允许最终整理，截断/传输中断在原会话恢复，无答案反馈。不是重新采集手机数据，本轮复用上一阶段三轮 unfixed 实机数据。</p>
<p>HapRay 官方二进制完成 13 组数据解析（每组 3 perf + 3 trace），生成 agent 任务；模型通过限定到单案例的只读 MCP 读取源码、报告、数据库，禁用 shell/web/外部目录。39 份模型结果再由官方 root-cause CLI 渲染。评估对象为 HapRay + skill + LLM + harness 的组合，不是 HapRay CLI 静态规则单独的召回率。</p>
<p>匿名输入未包含 fixed 版本、修复补丁、案例名、Git 历史、标准答案或之前的对照结论。546 次正式出站请求未出现案例原名及已知答案路径。检查和目录隔离降低泄露风险，但不等于可证明不存在任意语义泄露；源码仍保留正常业务命名及其既有注释。</p>
<p>这些案例是之前已测得显著差异的 13 个正例，操作规模也已明确，因此任务比从任意真实应用中开放式发现缺陷容易。只进行了每 harness 每案例一次检测，不能估计随机性或稳健排名。</p>
<h2>需要注意的质量问题</h2><ul><li>C10：源码实际调用 <code>flush(): Promise&lt;void&gt;</code>，三种输出及原 benchmark 都混入同步阻塞说法。保留“逐次 flush 未合并”的定位命中，另记解释错误。<a href="https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/reference/apis-arkdata/js-apis-data-preferences.md#flush-1">OpenHarmony 官方 API</a>明确它异步持久化；预登记标准原文保留，勘误单独记录。</li>
<li>采样事件为 <code>sw-cpu-clock</code>；部分答案仍把样本权重称为指令数，或把重叠 trace 切片时长当成 CPU 占比。这些数字不应直接采用。</li>
<li>抽查 C05 三轮均为 3000 个 Insert 切片；C13 三轮 QuerySql 分别是 201、209、201 次。OpenCode 将其描述为每轮 201 次并不精确。切片计数可以佐证操作形态，不能直接证明调用来源或全部因果关系。</li>
<li>C09 日志物化主要由源码识别，动态数据主要显示布局负载。C06 串行 await 也主要依赖源码，CPU 样本不能量化网络等待。符号缺失、SO 聚合为空及部分帧/内存事件缺失限制了归因。</li>
<li>初始故障、格式恢复与漏检分开记录。DSH C01/C02/C05/C08 和 OpenCode C11 使用原会话恢复；DSH C03、Claude C12 做 JSON 语法修复，原文本保留。Claude C01 曾因错误 SQL 笛卡尔连接中断 MCP，之后恢复；后续 SQL 加 10 秒上限。</li></ul>
<h2>完整裁定记录</h2>{details}<h2>交付文件</h2><p><a href="graded-results.json">结构化评分</a> · <a href="deployment.txt">本机部署与使用说明</a> · <a href="evaluation-records.zip">原生记录、配置、skill 与评分包</a> · <a href="outbound-audit.zip">实际出站请求审计包</a> · <a href="blind-inputs-text.zip">匿名源码与文本证据</a></p>
<p><small>API key 没有写入报告、压缩包或 Git；本机凭据以 Windows DPAPI 加密保存。付费代理已停止。原始二进制数据和解析数据库继续保留在本机 work 目录及原测量仓库。</small></p></html>'''
(O/'report.html').write_text(page,encoding='utf-8')
guide=f'''本机部署与本次评测

工作目录：{B}
项目 Git 仓库：D:\\OhmBenchmark-main
HapRay 源码：{B/'HapRay'}
官方 CLI：{B/'hapray-release/runtime/tools/perf-testing/perf-testing.exe'}
OpenCode：{B/'harnesses/node_modules/opencode-windows-x64/bin/opencode.exe'}
Claude Code：{B/'harnesses/node_modules/@anthropic-ai/claude-code/bin/claude.exe'}
DSH：{B/'harnesses/node_modules/@deepseek-ai/dsh/lib/bin.js'}（必须使用 Node 24）
Node 24：C:\\Users\\30422\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe
Python：C:\\Users\\30422\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe

各案例原生配置位于 runs/eval1-<opencode|claude|dsh>-Cxx。
OpenCode/Claude 的 skill 在 .claude/skills/hapray；DSH 在 .agents/skills/hapray。
各 harness 的 provider 指向本机 127.0.0.1:18780，由 api_proxy.py 注入 DeepSeek 凭据。
模型：deepseek-flash。思考 high；最终纯整理关闭 thinking。
凭据 deepseek.credential.xml 使用当前 Windows 用户 DPAPI 加密，仅供代理读取。
代理已停止；查看现有报告不需要启动代理或付费调用。

复现解析（不调用 LLM）：查看 run_hapray.py 中 update/root-cause 命令。
本次结果 results/<harness>/Cxx/；输入 blind/Cxx/；原始数据 raw/Cxx/。
完整 native 事件 events.jsonl、工具调用 toolcalls.jsonl，恢复记录 resume-*.jsonl。
出站请求 api-audit/，费用记录 api-usage.json。账户原余额不交付。
判分脚本 grade_results.py 在冻结后运行；grading-criteria.json 保留预登记原文。
C10 同步/异步 API 勘误见 graded-results.json.errata。

现有 run_harness.py 是本轮一次性记录脚本，原路径重新运行会覆盖事件文件。
若要新增实验，应复制 runs/homes/results 到新命名空间，并为代理设置新预算基线；不要覆盖本次冻结数据。
现有代理预算基线与计数仍保留，因此重新启动不会自动获得新的 50 元额度。
费用：{cost['account_decrease_cny']:.2f} 元账户减少量，包含试跑及可能的账户其他使用；这不是按请求精确归属账单。

来源：https://github.com/SMAT-Lab/ArkAnalyzer-HapRay
DeepSeek 接入：https://api-docs.deepseek.com/guides/anthropic_api/
说明：本轮只运行这三种 harness，没有扩展其他工具。
'''
(O/'deployment.txt').write_text(guide,encoding='utf-8')
with zipfile.ZipFile(O/'evaluation-records.zip','w',zipfile.ZIP_DEFLATED) as z:
    for parent in ['results','runs']:
        for p in (B/parent).rglob('*'):
            if p.is_file() and p.suffix.lower() in ['.json','.jsonl','.txt','.md','.py','.ps1','.yml','.yaml','.log','.sh']:
                z.write(p,p.relative_to(B))
    for p in B.glob('*.py'):z.write(p,'scripts/'+p.name)
    for name in ['graded-results.json','grading-criteria.json','private-map.json','protocol.json','blind-audit.json','cost-summary.json','api-usage.json','dynamic-spotchecks.json']:z.write(B/name,name)
with zipfile.ZipFile(O/'outbound-audit.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in (B/'api-audit').glob('eval1-*'):z.write(p,p.name)
with zipfile.ZipFile(O/'blind-inputs-text.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in (B/'blind').rglob('*'):
        if p.is_file() and p.suffix.lower() in ['.ets','.ts','.json','.json5','.txt','.md'] and 'skill' not in p.parts:z.write(p,p.relative_to(B/'blind'))
print(json.dumps({'output':str(O),'counts':data['counts'],'cost':cost['account_decrease_cny']}))
