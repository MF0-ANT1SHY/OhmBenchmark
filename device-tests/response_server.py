"""Local real HTTP response fixture; no injected latency.

Serves one row carrying a single ~55 KB string field. Two properties matter:

  * expectDataType:OBJECT stops parsing bodies above roughly 64 KB, so the body
    must stay under that cap for the handler's success path to run.
  * A flat object graph (one object, one large string) keeps the shared
    parse/materialization cost low for both variants while the unfixed handler
    still serializes every byte; a many-small-rows body inflates the fixed
    baseline and drowns the logging-path delta.

HTTP/1.1 keep-alive removes per-request reconnect latency from the measured
window.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,time,sys
kb=int(sys.argv[1]) if len(sys.argv)>1 else 55
desc=('Runtime scheduling, storage and rendering performance. '*((kb*1024)//55))
payload=json.dumps({'code':10000,'message':'ok','data':[{'id':0,'title':'HarmonyOS interview question 0','description':desc}]},separators=(',',':')).encode()
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        print(json.dumps({'time':time.time(),'path':self.path,'bytes':len(payload)}),flush=True)
    def log_message(self,*args):pass
print('payload bytes='+str(len(payload)),flush=True)
ThreadingHTTPServer(('127.0.0.1',18766),Handler).serve_forever()
