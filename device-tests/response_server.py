"""Local real HTTP response fixture; no injected latency."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,time
payload=json.dumps({'code':10000,'message':'ok','data':[{'id':i,'title':f'HarmonyOS interview question {i}','description':'Runtime scheduling, storage and rendering performance. '*5} for i in range(30000)]},separators=(',',':')).encode()
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        print(json.dumps({'time':time.time(),'path':self.path,'bytes':len(payload)}),flush=True)
    def log_message(self,*args):pass
print('payload bytes='+str(len(payload)),flush=True)
ThreadingHTTPServer(('127.0.0.1',18766),Handler).serve_forever()
