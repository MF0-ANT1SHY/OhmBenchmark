from pathlib import Path
import subprocess,tarfile,io,json,gzip,random,re,shutil
base=Path(__file__).resolve().parent
repo=Path(r'D:\OhmBenchmark-main')
results=json.loads((repo/'measurements/results.json').read_text(encoding='utf-8'))
selected=[r['case'] for r in results['cases'] if r['status']=='明确差异']
random.Random(91827).shuffle(selected)
descriptions={
'browser_eager_history_load':'数据库已有 50,000 条浏览记录，跨 100 天；重新启动应用，观察最初 10 秒。',
'browser_history_delete_no_transaction':'数据库已有 1,000 条浏览记录，跨 5 天；执行清空历史操作。',
'browser_history_list_foreach':'数据库已有 1,000 条浏览记录；打开历史页面，执行三次滑动，观察 10 秒。',
'browser_insert_date_lookup_cache':'连续保存 1,000 条浏览记录。',
'sheafreader_unread_counts_n_plus_1':'数据库已有 200 个 RSS 订阅和 10,000 篇未读文章；读取订阅及未读数量。',
'sheafreader_extract_tag_tolowercase':'解析含 100 篇长多语言 HTML 正文的 RSS 文档。',
'sheafreader_refresh_feeds_sequential':'刷新 40 个本地 HTTP RSS 订阅，各返回 25 篇文章；服务器没有人工延时。',
'wanharmony_history_log_materialization':'准备 5,000 条浏览记录，通过 Navigation 打开历史页；测量原页面生命周期中的操作片段。',
'jingmo_random_poem_orderby_random':'数据库已有 50,000 首诗；请求随机诗歌 10 次。',
'jingmo_dataset_import_no_transaction':'向空数据库导入 3,000 首诗，等待数据库操作完成。',
'jingmo_sync_page_reimport':'数据库已有 50,000 首诗；再次向数据同步的导入方法提交同一批诗歌。未测量网络下载。',
'interviewapp_search_history_unbounded':'通过原历史存储接口准备 5,000 条搜索历史；连续读取完整历史 100 次。',
'interviewapp_search_history_sync_flush':'通过原历史存储接口连续写入 1,000 条搜索历史；测量窗口额外包含 3 秒等待，以观察异步写回。'}
mapping=[]
for i,name in enumerate(selected,1):
    anon=f'C{i:02d}';spec=json.loads((repo/'cases'/name/'case.json').read_text(encoding='utf-8'))
    target=base/'blind'/anon;source=target/'source';source.mkdir(parents=True,exist_ok=True)
    archive=subprocess.check_output(['git','-C',str(repo/spec['host_app']['local_path']),'archive',f'case/{name}/unfixed'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as t:
        for member in t:
            if not member.isfile():continue
            p=Path(member.name)
            if p.suffix not in ['.ets','.ts','.json','.json5']:continue
            if any(x in p.parts for x in ['node_modules','oh_modules','.git','build','.hvigor']):continue
            if '..' in p.parts or p.is_absolute():continue
            dest=source/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(t.extractfile(member).read())
    raw=base/'raw'/anon;raw.mkdir(parents=True,exist_ok=True)
    rounds=[]
    for n in range(1,4):
        original=repo/'measurements'/name/'unfixed'/f'run{n}'
        info=json.loads((original/'result.json').read_text(encoding='utf-8'))
        shutil.copy2(original/'perf.data',raw/f'run{n}.data')
        with gzip.open(original/'trace.txt.gz','rt',encoding='utf-8',errors='replace') as f:trace=f.read()
        trace=re.sub(r'OHMB/[A-Za-z0-9_]+','WORKLOAD/span',trace)
        (raw/f'run{n}.htrace').write_text(trace,encoding='utf-8')
        text=(original/'perf-report.txt').read_text(encoding='utf-8',errors='replace')
        for identifier in selected:text=text.replace(identifier,'workload')
        (target/f'native-profile-{n}.txt').write_text(text,encoding='utf-8')
        rounds.append({'run':n,'pid':info['pid'],'elapsed_ms':info['elapsed_ms']})
    (target/'workload.json').write_text(json.dumps({'id':anon,'description':descriptions[name],'bundle':spec['host_app']['bundle_name'],'rounds':rounds,'notes':'同一应用版本的三轮真实运行。没有参考版本。elapsed 为原业务方法或固定观察窗口；软件 CPU 时钟样本不能作为 CPU 指令数。测量入口为附加探针，源码提供未经探针修改的原始应用。'},ensure_ascii=False,indent=2),encoding='utf-8')
    mapping.append({'id':anon,'case':name,'bundle':spec['host_app']['bundle_name'],'pids':[r['pid'] for r in rounds]})
(base/'private-map.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared',len(mapping),'anonymous source/data inputs')
