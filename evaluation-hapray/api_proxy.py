"""Local credential/budget boundary; preserves the harness's provider protocol."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import subprocess,json,urllib.request,urllib.error,threading,time
B=Path(__file__).resolve().parent; AUDIT=B/'api-audit';AUDIT.mkdir(exist_ok=True)
pwsh=r'C:\Users\30422\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'
KEY=subprocess.check_output([pwsh,'-NoProfile','-Command',f"$s=Import-Clixml -LiteralPath '{B / 'deepseek.credential.xml'}'; [System.Net.NetworkCredential]::new('', $s).Password"],text=True).strip()
def balance():
    req=urllib.request.Request('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+KEY})
    with urllib.request.urlopen(req,timeout=30) as r:d=json.load(r)
    return sum(float(x['total_balance']) for x in d['balance_infos'] if x['currency']=='CNY')
BASELINE=sum(float(x['total_balance']) for x in json.loads((B/'balance-before.json').read_text(encoding='utf-8-sig'))['balance_infos'] if x['currency']=='CNY')
lock=threading.Lock();usage=json.loads((B/'api-usage.json').read_text(encoding='utf-8')) if (B/'api-usage.json').exists() else [];counts={}
for u in usage:counts[u['run']]=max(counts.get(u['run'],0),u['request'])
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def send_json(self,status,value):
        data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path.endswith('/models'):
            return self.send_json(200,{'object':'list','data':[{'id':'deepseek-flash','object':'model','created':0,'owned_by':'deepseek'}]})
        self.send_json(404,{'error':'Unknown route'})
    def do_POST(self):
        segments=self.path.split('/');run=segments[1];route='/'+'/'.join(segments[2:])
        if not route.split('?')[0].endswith(('/chat/completions','/messages')):
            return self.send_json(404,{'error':'Endpoint not enabled'})
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with lock:
            spent=BASELINE-balance();n=counts.get(run,0)+1
            if spent>=45 or n>26:
                return self.send_json(429,{'error':{'type':'budget_limit','message':'Evaluation budget or per-session request limit reached; return existing findings.'}})
            counts[run]=n
        body['model']='deepseek-flash';body['max_tokens']=min(body.get('max_tokens',8192),8192)
        body.pop('max_completion_tokens',None)
        if n>=14:
            body.pop('tools',None);body.pop('tool_choice',None)
            reminder='The fixed analysis budget is now exhausted. Do not call further tools. Return the final JSON summary and up to 5 supported suspects using only evidence already gathered. State uncertainty; do not invent missing evidence.'
            messages=body.get('messages',[])
            if messages and messages[-1].get('role')=='user':
                content=messages[-1]['content']
                if isinstance(content,list):content.append({'type':'text','text':reminder})
                else:messages[-1]['content']=str(content)+'\n'+reminder
            else:messages.append({'role':'user','content':reminder})
        else:body['max_tokens']=min(body['max_tokens'],4096)
        if route.endswith('/chat/completions'):
            body['thinking']={'type':'enabled'};body['reasoning_effort']='high'
            if body.get('stream'):body['stream_options']={'include_usage':True}
        else:
            body['thinking']={'type':'enabled','budget_tokens':4096}
            body['output_config']={'effort':'high'}
        if n>=14:
            body['thinking']={'type':'disabled'}
            body.pop('reasoning_effort',None);body.pop('output_config',None)
            body['max_tokens']=6000
        prefix=AUDIT/f'{run}-{n:03d}'
        prefix.with_suffix('.request.json').write_text(json.dumps(body,ensure_ascii=False),encoding='utf-8')
        headers={'Content-Type':'application/json','Authorization':'Bearer '+KEY,'x-api-key':KEY,'anthropic-version':'2023-06-01'}
        req=urllib.request.Request('https://api.deepseek.com'+route,data=json.dumps(body).encode(),headers=headers)
        started=time.time();record={'run':run,'request':n,'spent_cny_before':round(spent,5),'model':body['model']}
        try:
            response=urllib.request.urlopen(req,timeout=300)
        except urllib.error.HTTPError as e:
            raw=e.read();record.update(status=e.code,error=raw.decode(errors='replace')[:1000]);self.send_json(e.code,{'error':record['error']})
        else:
            self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','application/json'));self.send_header('Connection','close');self.end_headers();self.close_connection=True
            raw=bytearray()
            try:
                while data:=response.readline():
                    raw.extend(data);self.wfile.write(data);self.wfile.flush()
                    if data.startswith(b'data: '):
                        try:
                            event=json.loads(data[6:]);u=event.get('usage') or event.get('message',{}).get('usage')
                            if u:record.setdefault('usage',{}).update(u)
                        except ValueError:pass
            except (BrokenPipeError,ConnectionResetError):record['client_disconnected']=True
            prefix.with_suffix('.response.txt').write_bytes(raw)
            if not body.get('stream'):
                try:record['usage']=json.loads(raw).get('usage',{})
                except ValueError:pass
            record['status']=response.status;response.close()
        record['elapsed_s']=round(time.time()-started,2)
        with lock:
            usage.append(record);(B/'api-usage.json').write_text(json.dumps(usage,indent=2),encoding='utf-8')
        print(run,n,record.get('status'),'spent before',record['spent_cny_before'],flush=True)
if __name__=='__main__':
    print('Local DeepSeek proxy ready on 127.0.0.1:18780; stop threshold CNY 45',flush=True)
    ThreadingHTTPServer(('127.0.0.1',18780),Handler).serve_forever()
