"""Ordinary deterministic song search, with no measurement endpoints."""
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs,urlsplit

TITLES=('Dawn','Night Drive','Blue Horizon','Afterglow','City Lights','Rainfall','Northern Sky','Daybreak','Ocean Waves','Quiet Streets','Neon Garden','Sunrise','Moonlight','Summer Breeze','Cloud Atlas','New World','Starlight','Lost Signal','Open Road','Homecoming')
CATALOGUE=[{'img':'http://127.0.0.1:18493/cover.svg','name':'Electronic '+title,'creator':'Studio '+str(i%5+1),'time':180+i*7} for i,title in enumerate(TITLES)]
COVER=b'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="#182345"/><circle cx="40" cy="40" r="27" fill="#526dd9"/><circle cx="40" cy="40" r="9" fill="#182345"/></svg>'

def search(keyword):
    needle=keyword.casefold().strip()
    return [row for row in CATALOGUE if needle and needle in (row['name']+' '+row['creator']).casefold()]

def response(path):
    url=urlsplit(path);query=parse_qs(url.query)
    if url.path=='/search' and set(query)=={'keyword'} and len(query['keyword'])==1:
        return 200,'application/json',json.dumps(search(query['keyword'][0]),ensure_ascii=False,separators=(',',':')).encode()
    if url.path=='/cover.svg' and not url.query:return 200,'image/svg+xml',COVER
    return 404,'text/plain',b'Not found'

def handler(observe=None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            import time
            start=time.monotonic();status,content_type,body=response(self.path);sent=0;error=None
            try:
                self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers()
                self.wfile.write(body);self.wfile.flush();sent=len(body)
            except (BrokenPipeError,ConnectionResetError) as exc:error=type(exc).__name__
            finally:
                if observe:observe(self.path,start,time.monotonic(),status,body,sent,error)
        def log_message(self,*args):pass
    return Handler
