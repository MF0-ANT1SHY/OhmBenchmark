"""Package the collected evidence and a concise, explicit results report."""
from pathlib import Path
import json, statistics, html, zipfile, shutil

root=Path(__file__).resolve().parents[1]
out=Path(r'C:\Users\30422\Documents\Codex\2026-10-01\goal-project-git-pura-70-case\outputs')
out.mkdir(exist_ok=True)
rows=json.loads((root/'measurements/summary.json').read_text(encoding='utf-8'))
specs={p.parent.name:json.loads(p.read_text(encoding='utf-8')) for p in (root/'cases').glob('*/case.json')}
weak={
 'sheafreader_insert_duplicate_exception':'重复插入：两版范围重叠，差异不稳定。',
 'sheafreader_article_list_foreach':'真实列表滚动：CPU 中位数仅降低约 12%；两版组件出现数均为 37，未支持声明的组件创建差异。',
 'weatherassistant_http_session_leak':'120 次真实 HTTP 请求后，各轮 FD 数量均不增长，耗时/CPU 无稳定改善。',
 'cloudmusic_local_song_memory_filter':'1,000 首元数据，原页面检索方法调用 10 次；未出现稳定改善。只测处理方法，不测结果绘制。'
}
notes={
 'browser_eager_history_load':'50,000 条历史；真实冷进程启动，比较前 10 秒 CPU，不是启动完成耗时。',
 'browser_history_list_foreach':'1,000 条历史，真实打开历史和 3 次滑动；10 秒 CPU；组件出现数每轮 200→59。',
 'browser_history_delete_no_transaction':'1,000 条历史、5 天；原 deleteAll；结束后历史为空。',
 'browser_insert_date_lookup_cache':'1,000 次原页面记录保存；日期查询每轮 1,000→1，实际插入仍为 1,000。',
 'sheafreader_unread_counts_n_plus_1':'200 个订阅、10,000 篇未读；原方法返回未读总数 10,000；查询 201→2。',
 'sheafreader_extract_tag_tolowercase':'100 篇长多语言 HTML；原解析器完整返回 100 篇。300 篇导致冻结的探索数据另存。',
 'sheafreader_refresh_feeds_sequential':'40 个真实本地 HTTP RSS，每个 25 篇；实际数据库均 1,000 篇。固定版返回 inserted=250，存在并发计数问题。',
 'wanharmony_history_log_materialization':'5,000 条历史，真实 HistoryPage 导航后执行原生命周期日志体。仅支持该日志阶段，不等于整个页面或 title-event 耗时。',
 'jingmo_random_poem_orderby_random':'50,000 条诗歌；原随机查询 10 次，均返回 10 条。',
 'jingmo_dataset_import_no_transaction':'3,000 条原 DAO 写入，等待真实完成；两版数据库均 3,000 条。',
 'jingmo_sync_page_reimport':'数据库已有 50,000 条，调用原重复导入方法；只证明数据库工作减少，不证明网络下载减少。',
 'interviewapp_search_history_unbounded':'5,000 条原 HistoryStore 历史；100 次读取。返回总数 500,000→2,000，固定版有意只保留 20 条。',
 'interviewapp_search_history_sync_flush':'原 setItem 1,000 次；两版均额外等待 3 秒覆盖防抖写回。主指标 CPU；未修复版有 3 秒卡顿告警但全部完成且存活。'
}
cpu_cases={'browser_eager_history_load','browser_history_list_foreach','interviewapp_search_history_sync_flush'}
case_rows=[]
for name,spec in sorted(specs.items()):
    series=[r for r in rows if r['case']==name]
    variants={v:sorted([r for r in series if r['variant']==v],key=lambda r:r['run']) for v in ['unfixed','fixed']}
    if len(series)==6:
        status='未复现稳定改善' if name in weak else '明确差异'
    elif name=='interviewapp_response_log_full_stringify': status='阻塞'
    else: status='未完成测试'
    key='trace_cpu_ms' if name in cpu_cases else 'elapsed_ms'
    item={'case':name,'status':status,'metric':key,'note':notes.get(name,weak.get(name,'')),'rounds':variants}
    if len(series)==6:
        u=[r[key] for r in variants['unfixed']]; f=[r[key] for r in variants['fixed']]
        item.update(unfixed_median=statistics.median(u),fixed_median=statistics.median(f),reduction_percent=(1-statistics.median(f)/statistics.median(u))*100,nonoverlapping=max(f)<min(u))
    if status=='阻塞':item['note']='本地响应在原 SDK 路径中返回字符串，未通过原 success-code 判断；更早尝试超过 5 MiB 默认响应限制。未强制转换以制造成功路径。'
    if status=='未完成测试':item['note']='本轮时间范围内未完成。'+('项目未提供 ytmusic host bundle。' if name.startswith('ytmusic_') else '')
    case_rows.append(item)

result={'repository':str(root),'device':'HUAWEI Pura 70 Ultra / HBP-AL00','device_build':'HBP-AL00 6.0.0.112(SP55C00E112R5P4)','started_local':'2026-10-01 00:57:57 +08:00','cases':case_rows}
(out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'measurements/results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(root/'measurements/summary.json',out/'rounds.json')

def package(destination, files):
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for p in files:
            if p.is_file():z.write(p,p.relative_to(root).as_posix())
    print(destination.name,round(destination.stat().st_size/1024/1024,1),'MiB',flush=True)

for item in case_rows:
    name=item['case']; p=root/'measurements'/name
    if not p.exists():continue
    files=list(p.rglob('*'))+list((root/'device-tests/patches'/name).glob('*'))+list((root/'cases'/name).glob('*'))
    package(out/(name+'.zip'),files)
package(out/'methods-and-source.zip',list((root/'device-tests').rglob('*'))+list((root/'hosts_patches').rglob('*.patch'))+[root/'hosts_patches/host-reconstruction.json',root/'hosts_patches/REPRODUCE.md']+list((root/'cases').rglob('*'))+[root/'measurements/README.md',root/'measurements/native-rdb-events.json',root/'measurements/summary.json',root/'measurements/results.json'])
package(out/'excluded-experiments.zip',list((root/'experiments').rglob('*')))

esc=html.escape
success=sum(i['status']=='明确差异' for i in case_rows)
body=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Pura 70 实测结果</title>
<style>body{{max-width:1500px;margin:35px auto;padding:0 24px;font:16px/1.7 system-ui;color:#172337;background:#fafbfd}}h1,h2{{line-height:1.3}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border:1px solid #d4dce5;padding:9px;text-align:left;vertical-align:top}}th{{background:#eaf0f7}}.good{{color:#087047}}.weak{{color:#985c00}}code{{font-size:13px}}a{{color:#075ac4}}summary{{cursor:pointer}}small{{color:#526174}}</style>
<h1>Pura 70：性能案例真实设备数据</h1><p><b>{success} 个案例在受控工作负载下呈现明确差异，每个 fixed / unfixed 各 3 轮，共 {success*6} 轮成功数据。</b>另有 4 个案例没有稳定改善，1 个阻塞；其余 12 个本轮未完成。没有把未复现或中断数据计入成功数。</p>
<p>项目已初始化 Git：<code>D:\\OhmBenchmark-main</code>。设备故障报告识别为 HUAWEI Pura 70 Ultra（HBP-AL00），系统构建 6.0.0.112(SP55C00E112R5P4)。任务从 2026-10-01 00:57:57 开始，预算截止 03:57:57（北京时间）。</p>
<p>每个数据包含实际测试 HAP、同版测量补丁、原 case / fix.patch，以及六轮 hitrace 原文（gzip）、hiperf 原始 perf.data、perf stat、原生热点报告、结果和运行日志。界面截图/布局随相应轮次保留。<a href="methods-and-source.zip">测量方法、原始 host bundles 与脚本</a>；<a href="excluded-experiments.zip">被排除的探索与故障数据</a>；<a href="results.json">结构化结果</a>；<a href="rounds.json">逐轮数据</a>。</p>
<h2>如何解释结果</h2><p>这些是真实应用、真实 Ark 运行时和真实数据库/HTTP 上执行的原业务方法。除明确标出的真实启动、导航和滚动实验外，使用应用内测量入口调起原方法，不能等同所有案例都经过完整手工点击路径。数据准备在测量前；没有用人工延时模拟 bug。刷新 RSS / 天气使用本地真实 HTTP 固定响应。</p>
<p>表中是三轮中位数，括号内展开可查看全部三轮；单位毫秒。CPU 根据目标进程所有可观测线程在 OHMB 标记内的调度区间求和。启动/滚动使用固定 10 秒窗口；同步 flush 含两版相同 3 秒等待，因此这些以 CPU 为主指标。perf 采样与计数覆盖稍宽的启停窗口，硬件计数覆盖率原样保留；部分 ArkTS 栈未完全符号化。不能用请求的 1000 Hz 直接换算 sample count 为 CPU。</p>
<p>“明确差异”指本次受控负载下效应较大且三轮范围不重叠，不是三次测量就证明总体统计显著性。记录按版本成组运行而非随机交错，负载规模包含压力场景，不能外推日常延迟。不同测量路径与原 benchmark oracle 的差异均在备注披露。</p>
<table><thead><tr><th>案例 / 数据包</th><th>结论</th><th>主指标</th><th>unfixed → fixed 中位数</th><th>降低</th><th>范围、实际路径与限制</th></tr></thead><tbody>'''
for item in case_rows:
    n=item['case']; status=item['status']; vs=item['rounds']; measured='unfixed_median' in item
    name=f'<a href="{n}.zip"><code>{n}</code></a>' if (out/(n+'.zip')).exists() else f'<code>{n}</code>'
    detail=''
    if measured:
        for v in ['unfixed','fixed']:
            elapsed=', '.join(f"{r['elapsed_ms']:.3f}" for r in vs[v]);cpu=', '.join(f"{r['trace_cpu_ms']:.3f}" if 'trace_cpu_ms' in r else '缺少标记' for r in vs[v])
            detail+=f'<p>{v}：elapsed [{elapsed}]；CPU [{cpu}]</p>'
        detail='<details><summary>三轮原始数值</summary>'+detail+'</details>'
    med=f"{item['unfixed_median']:.3f} → {item['fixed_median']:.3f}" if measured else '—'
    reduction=f"{item['reduction_percent']:.1f}%" if measured else '—'
    metric=('CPU' if item['metric']=='trace_cpu_ms' else 'elapsed') if measured else '—'
    body+=f'<tr><td>{name}</td><td class="{"good" if status=="明确差异" else "weak"}">{status}</td><td>{metric}</td><td>{med}</td><td>{reduction}</td><td>{esc(item["note"])}{detail}</td></tr>'
body+='''</tbody></table><h2>实际检查与保留事项</h2><p>运行中发现并处理了通知权限弹窗和熄屏；不把停在弹窗或中断的运行计入成功。Sheaf 的 tablet/PC manifest 对两版一致扩展为 phone；CloudMusic 对两版移除与检索无关的悬浮窗权限。300 篇 RSS 和 10,000 首歌曲准备阶段的冻结、安装失败导致的误标轮次、被并行报告处理干扰的轮次等都单独保留，原因见实验包。后续正式数据重新完整采集。</p><p>RSS 并发刷新固定版虽然数据库实际有 1,000 篇，但返回 inserted=250，存在返回计数的功能问题；这不影响已观察的耗时差异，但不能据此宣布修复功能完全正确。天气 HTTP 泄漏未复现；重复插入与文章列表未达到稳定明确效果。京墨重复导入的网络零传输声明没有得到本次证实。</p></html>'''
(out/'report.html').write_text(body,encoding='utf-8')
print('report',success,'successful cases',len(rows),'rounds',flush=True)
