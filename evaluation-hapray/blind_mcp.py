"""Read-only tools rooted at one anonymous case; no shell or outside filesystem."""
import sys,json,re,sqlite3,time
from pathlib import Path
sys.stdin.reconfigure(encoding='utf-8');sys.stdout.reconfigure(encoding='utf-8')
root=Path(sys.argv[1]).resolve();audit=Path(sys.argv[2])
def path(name):
    p=(root/name).resolve()
    if not p.is_relative_to(root):raise ValueError('Outside case workspace')
    return p
def files(pattern):return [p for p in root.rglob(pattern) if p.is_file() and '.git' not in p.parts]
def schema(name,description,props,required):return {'name':name,'description':description,'inputSchema':{'type':'object','properties':props,'required':required}}
tools=[
schema('list_files','List files in this case only; use glob e.g. source/**/*.ets or hapray/**/*.json.',{'pattern':{'type':'string'}},['pattern']),
schema('read_file','Read a UTF-8 source/report/skill file with line numbers (max 180 lines).',{'path':{'type':'string'},'start_line':{'type':'integer'},'lines':{'type':'integer'}},['path']),
schema('search','Search text within the case using a regex and file glob; returns up to 60 matches.',{'pattern':{'type':'string'},'glob':{'type':'string'}},['pattern','glob']),
schema('sql','Read-only SQLite query on a HapRay database. No ATTACH, extension loading or writes.',{'path':{'type':'string'},'query':{'type':'string'}},['path','query'])]
def call(name,a):
    if name=='list_files':return '\n'.join(str(p.relative_to(root)).replace('\\','/') for p in files(a['pattern']))[:20000]
    if name=='read_file':
        p=path(a['path'])
        if p.suffix.lower() not in ['.json','.jsonl','.ets','.ts','.md','.txt','.json5','.log','.yml']:raise ValueError('Use SQL for databases; raw binary not exposed')
        lines=p.read_text(encoding='utf-8',errors='replace').splitlines();start=max(1,a.get('start_line',1));n=min(180,a.get('lines',120))
        return f'Total lines: {len(lines)}\n'+'\n'.join(f'{i+1}: {s}' for i,s in enumerate(lines[start-1:start-1+n],start-1))[:22000]
    if name=='search':
        regex=re.compile(a['pattern'],re.I);found=[]
        for p in files(a['glob']):
            if p.suffix not in ['.ets','.ts','.json','.md','.txt','.json5']:continue
            for i,line in enumerate(p.read_text(encoding='utf-8',errors='replace').splitlines(),1):
                if regex.search(line):found.append(f'{p.relative_to(root)}:{i}: {line[:350]}')
                if len(found)>=60:return '\n'.join(found)
        return '\n'.join(found)
    if name=='sql':
        p=path(a['path']);con=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
        deadline=time.monotonic()+10;con.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
        con.set_authorizer(lambda action,*args:sqlite3.SQLITE_DENY if action in [sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH,sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE,sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_DROP_TABLE] else sqlite3.SQLITE_OK)
        q=con.execute(a['query']);value={'columns':[c[0] for c in q.description] if q.description else [],'rows':q.fetchmany(100)};con.close();return json.dumps(value,ensure_ascii=False)[:22000]
    raise ValueError('Unknown tool')
for line in sys.stdin:
    try:
        req=json.loads(line);method=req.get('method');rid=req.get('id')
        if rid is None:continue
        if method=='initialize':result={'protocolVersion':req['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'blind-evidence','version':'1.0'}}
        elif method=='tools/list':result={'tools':tools}
        elif method=='tools/call':
            params=req['params'];a=params.get('arguments',{})
            try:text=call(params['name'],a);result={'content':[{'type':'text','text':text}]}
            except Exception as e:result={'content':[{'type':'text','text':str(e)}],'isError':True}
            with audit.open('a',encoding='utf-8') as f:f.write(json.dumps({'tool':params['name'],'arguments':a,'error':result.get('isError',False)},ensure_ascii=False)+'\n')
        elif method=='ping':result={}
        else:result={}
        print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result},ensure_ascii=False),flush=True)
    except Exception:pass
