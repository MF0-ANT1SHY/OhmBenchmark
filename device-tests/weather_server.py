from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
import json,time
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def do_GET(self):
        city=int(parse_qs(urlparse(self.path).query).get('city',['440300'])[0])
        casts=[dict(date=f'2026-10-{i+1:02}',week=4+i,dayweather='晴',nightweather='晴',daytemp=26,nighttemp=20,daywind='南',nightwind='南',daypower='1-3',nightpower='1-3',daytemp_float=26,nighttemp_float=20) for i in range(4)]
        payload=json.dumps(dict(status='1',count=1,infocode=10000,forecasts=[dict(city='Test City',adcode=city,casts=casts)]),ensure_ascii=False).encode()
        self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        print(json.dumps(dict(time=time.time(),path=self.path,client=self.client_address,bytes=len(payload))),flush=True)
    def log_message(self,*args):pass
ThreadingHTTPServer(('127.0.0.1',18767),Handler).serve_forever()
