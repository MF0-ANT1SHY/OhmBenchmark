#!/usr/bin/env python3
"""Ordinary RSS/OPML/article data for the reader's existing subscription UI."""
import argparse
import html
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import re
from urllib.parse import urlsplit


class Catalogue:
    def __init__(self,base_url,feeds=10,articles=100,body_bytes=32768):
        if min(feeds,articles,body_bytes)<1:
            raise ValueError('positive ordinary catalogue sizes required')
        self.base=base_url.rstrip('/');self.feeds=feeds;self.articles=articles
        paragraph='<p>Reading Notes: Landscapes, languages, and everyday observations enrich a quiet afternoon.</p>'
        self.body='<html><body>'+paragraph*((body_bytes+len(paragraph)-1)//len(paragraph))+'</body></html>'

    def feed(self,number):
        if not 1<=number<=self.feeds:raise KeyError('feed')
        entries=[]
        for article in range(1,self.articles+1):
            title=f'Journal {number} article {article}'
            link=f'{self.base}/articles/{number}/{article}.html'
            entries.append(f'<item><title>{title}</title><link>{link}</link>'
                           f'<guid isPermaLink="false">journal-{number}-{article}</guid>'
                           '<author>Reader</author><pubDate>Thu, 01 Oct 2026 00:00:00 GMT</pubDate>'
                           f'<description><![CDATA[{self.body}]]></description></item>')
        xml='<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        xml+=f'<title>Journal {number}</title><link>{self.base}</link><description>Reading journal</description>'
        return (xml+''.join(entries)+'</channel></rss>').encode()

    def opml(self):
        entries=[f'<outline type="rss" text="Journal {i}" title="Journal {i}" '
                 f'xmlUrl="{html.escape(self.base,quote=True)}/feeds/{i}.xml"/>'
                 for i in range(1,self.feeds+1)]
        return ('<?xml version="1.0"?><opml version="2.0"><head><title>Reading journals</title></head>'
                '<body>'+''.join(entries)+'</body></opml>').encode()

    def response(self,path):
        if path=='/subscriptions.opml':return 'text/x-opml; charset=utf-8',self.opml()
        match=re.fullmatch(r'/feeds/([1-9][0-9]*)\.xml',path)
        if match:return 'application/rss+xml; charset=utf-8',self.feed(int(match[1]))
        match=re.fullmatch(r'/articles/([1-9][0-9]*)/([1-9][0-9]*)\.html',path)
        if match and 1<=int(match[1])<=self.feeds and 1<=int(match[2])<=self.articles:
            return 'text/html; charset=utf-8',self.body.encode()
        raise KeyError(path)


def handler(catalogue):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            try:mime,payload=catalogue.response(urlsplit(self.path).path);status=200
            except KeyError:mime,payload,status='text/plain',b'Not found',404
            self.send_response(status);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    return Handler


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=18491)
    parser.add_argument('--base-url',default='http://127.0.0.1:18491')
    parser.add_argument('--feeds',type=int,default=10);parser.add_argument('--articles',type=int,default=100)
    parser.add_argument('--body-bytes',type=int,default=32768)
    args=parser.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),handler(Catalogue(args.base_url,args.feeds,args.articles,args.body_bytes)))
    print(f'RSS data service listening on {args.host}:{args.port}',flush=True);server.serve_forever()
