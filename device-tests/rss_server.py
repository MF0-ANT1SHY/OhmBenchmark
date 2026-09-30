"""Deterministic RSS fixture server. No injected delay or throttling."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, time
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        feed=self.path.rsplit('/',1)[-1]
        items=''.join(f'<item><title>Feed {feed} article {i}</title><link>https://example.org/{feed}/{i}</link><guid>feed-{feed}-article-{i}</guid><description>Engineering article {i}</description><pubDate>Wed, 30 Sep 2026 12:00:00 GMT</pubDate></item>' for i in range(25))
        payload=f'<rss version="2.0"><channel><title>Engineering feed {feed}</title><link>https://example.org/</link><description>Controlled feed</description>{items}</channel></rss>'.encode()
        self.send_response(200); self.send_header('Content-Type','application/rss+xml; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload)
        print(json.dumps({'time':time.time(),'path':self.path,'bytes':len(payload)}),flush=True)
    def log_message(self,*args): pass
ThreadingHTTPServer(('127.0.0.1',18765),Handler).serve_forever()
