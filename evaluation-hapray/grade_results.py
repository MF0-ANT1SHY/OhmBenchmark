from pathlib import Path
import json,datetime
B=Path(__file__).resolve().parent
criteria=json.loads((B/'grading-criteria.json').read_text(encoding='utf-8'))['cases']
# Post-freeze manual adjudication. No grades are fed back to any detector.
selected={
'opencode':[1,1,1,2,1,0,1,1,1,1,1,1,3],
'claude':[1,1,1,1,1,1,1,1,4,1,1,1,1],
'dsh':[1,1,4,1,1,1,1,1,4,1,2,1,1]}
exceptions={
('opencode','C06'):('miss','主要诊断逐篇数据库插入与 Promise 开销；未指出 refreshAllFeeds 逐源串行 await 这个目标机制。'),
('opencode','C13'):('partial','从 201 次 QuerySql 推断 N+1 并建议 GROUP BY，但仅给 DatabaseManager 文件、行号 0，未定位 getFeedsWithCounts/getUnreadCount 调用点。机制命中，源码定位不足。'),
('claude','C08'):('partial','把热点归因于 SearchHistoryComp 全量渲染，未定位实际重复读取的 HistoryStore.getAll 全表物化；写入侧也误称 putSync 直接落盘。'),
('claude','C09'):('partial','在 WebPage.onTitleReceive 指出全量日志，但未指出本次目标 HistoryPage.aboutToAppear 的 map/stringify 日志。相似机制出现在错误调用点。'),
('claude','C13'):('partial','识别 SQLite/ResultSet 读取热点并建议 COUNT，但无源码函数/行号，未识别逐 feed COUNT 的 N+1 机制。')}
notes={
'C01':'定位随机排序的全表工作；SQL 复杂度与投影列开销的细节存在夸大，额外嫌疑未逐项验证。',
'C02':'定位嵌套 ForEach。组件构建 200 次与场景 1000 条不等价，不能由复用率 0 推出所有条目同时构建。',
'C03':'定位冷启动全历史读取。关于 forEach(async) 串行/并行、返回时序和空刷的附加解释不能一概采信。',
'C04':'定位 extractTag 每标签整串 toLowerCase；OpenCode 将 parseDate 排第一并推测日期含长正文，缺乏证据。',
'C05':'定位单条 insert 缺批量事务。模型有把 trace 累计切片时长、CPU 样本权重和 wall time 混用的情况。',
'C06':'目标是逐订阅串行刷新；数据库写入热点不等于已检测到该串行机制。未用修复版数据提示模型。',
'C07':'定位逐行 DELETE/独立提交。实际测量由探针调用原方法，UI 清空入口是否调用它是另一个问题。',
'C08':'操作级命中指向 getAll 的全量物化及随历史量增加的工作；建议缓存/限读不等于完整实现 MAX_ENTRIES 存储裁剪。',
'C09':'目标是 HistoryPage.aboutToAppear 的整表日志物化；UI 布局热点不能直接证明日志占据 CPU。',
'C10':'源码实际是异步 flush()，不是 flushSync()。三种结果均定位每次 setItem 都 flush 并建议合并，但均含同步阻塞错误。原 benchmark 及预登记标准的同步措辞也错误；依据源码和补丁明确勘误，不改写原标准。',
'C11':'定位已有数据仍无条件批量导入。批量写入本身不是缺陷，目标是重复执行这批工作。',
'C12':'定位 insertDate 的重复日期查询，并建议日期缓存。其他候选如删除路径不属于本次触发。',
'C13':'目标是 getFeedsWithCounts 逐 feed 调用 getUnreadCount；仅看到 SQLite 热点不能算完整命中。'}
dynamic={
'C01':'间接：SQLite/RDB 采样与目标 SQL 一致，未获得 SQL 级直接计时。',
'C02':'操作级：组件构建和帧指标；没有 ForEach 单函数计时。',
'C03':'间接：查询数量/取值与启动期样本相符；部分任务只复核一轮。',
'C04':'较强相关：三轮 ICU/ToLower 热点与源码重复小写转换相符，仍无应用行号栈。',
'C05':'操作级：三轮大量 Insert 切片；不能用切片累加值充当 CPU 占比。',
'C06':'源码为主：串行 await 清楚，CPU 样本不能直接量化网络等待或并发收益。',
'C07':'间接：删除路径、RDB/同步 I/O 样本相关，缺应用函数级归因。',
'C08':'较强相关：三轮字符串物化/NAPI/Preferences 热点；未独立验证模型每一个百分比。',
'C09':'源码为主：日志语句存在，动态数据主要显示布局和主线程负载，未隔离日志耗时。',
'C10':'间接：Preferences/XML/文件写回栈支持写放大，不支持主线程同步等待断言。',
'C11':'间接：ValuesBucket/JSI/RDB 栈与重复导入相符，数据已存在是场景事实。',
'C12':'间接：查询/插入与高频 RDB 调度相符，日期缓存收益需修复对照另证。',
'C13':'操作级：201 次 QuerySql 与 200 feed 场景吻合；DSH 结合源码定位。'}
rows=[]
for c in criteria:
    for h in ['opencode','claude','dsh']:
        root=B/'results'/h/c['id'];p=json.loads((root/'prediction.json').read_text(encoding='utf-8'))
        rank=selected[h][int(c['id'][1:])-1]
        status,reason=exceptions.get((h,c['id']),('hit','目标操作的浪费机制与相关源码函数/位置均被指出。'))
        suspect=next((s for s in p['suspects'] if s.get('rank')==rank),None)
        rows.append(dict(id=c['id'],case=c['case'],harness=h,verdict=status,matched_rank=rank or None,reason=reason,
            target=c,selected_prediction=suspect,dynamic_support=dynamic[c['id']],quality_note=notes[c['id']],
            initial_status=json.loads((root/'status.json').read_text()),resume=(root/'resume-status.json').exists(),serialization_repair=(root/'serialization-repair.json').exists()))
counts={h:{s:sum(r['harness']==h and r['verdict']==s for r in rows) for s in ['hit','partial','miss']} for h in selected}
result={'frozen_at':json.loads((B/'blind-audit.json').read_text())['time'],'graded_at':datetime.datetime.now().isoformat(),
'scoring':'Manual post-freeze top-5 mechanism + specific source-location matching. Hit measures target localization, not correctness of every explanation or patch. Partial excluded from hit count.',
'counts':counts,'rows':rows,'errata':{'C10':'Original case text and preregistered criterion incorrectly say synchronous flush/flushSync. Actual source calls asynchronous flush(); patch debounces calls. Count target repeated-flush localization separately from the shared API-semantics error.',
'reference':'https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/reference/apis-arkdata/js-apis-data-preferences.md#flush-1'}}
(B/'graded-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(counts))
