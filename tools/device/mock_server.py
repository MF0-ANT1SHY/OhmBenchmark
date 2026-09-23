#!/usr/bin/env python3
"""Local mock backend for cases whose public endpoints are dead.

Served on 127.0.0.1:8978 (host); expose to device with:
    hdc rport tcp:8978 tcp:8978      # device localhost:8978 -> host 8978

Endpoints:
  /feed<N>.xml            RSS2 feed with 60 long items (sheafreader add-feed/refresh)
  /search?keyword=...     ytmusic search  -> SongProps[] (names = bundled mp3s)
  /randomSongs?count=N    ytmusic playlist -> SongProps[]
  /icon<N>.jpeg           tiny jpeg (weatherassistant icon stand-in)
  /page/<tag>[.com]       tiny HTML page (browser history seeding)
"""
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from xml.sax.saxutils import escape

YT_MP3_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          'hosts', 'ytmusic', 'entry', 'src', 'main', 'resources', 'rawfile', 'audio')
SONGS = [f[:-4] for f in os.listdir(YT_MP3_DIR) if f.endswith('.mp3')] if os.path.isdir(YT_MP3_DIR) else []

# standard 1x1 white JPEG; scaled by the app, enough to exercise decode/paint
import base64 as _b64
ICON = _b64.b64decode(
    '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a'
    'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA'
    'AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q==')


def rss(path):
    m = re.match(r'/feed(\d+)\.xml', path)
    n = int(m.group(1)) if m else 0
    items = []
    for i in range(60):
        body = (' '.join(['lorem ipsum dolor sit amet consectetur adipiscing elite'] * 40)) + f' feed{n} item{i} 标签Tag{i} 混合内容'
        items.append(f'<item><title>Feed{n} Article {i}: 性能基准测试文章标题较长的示例</title>'
                     f'<link>https://example.com/feed{n}/{i}</link>'
                     f'<description>{escape(body)}</description>'
                     f'<pubDate>Thu, 18 Sep 2026 10:0{i % 10}:00 GMT</pubDate></item>')
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f'<title>OhmBench Feed {n}</title><link>https://example.com</link>'
            f'<description>mock feed {n}</description>' + ''.join(items) + '</channel></rss>').encode()


def songs(count):
    out = []
    for i in range(min(int(count), len(SONGS) * 3)):
        name = SONGS[i % len(SONGS)]
        out.append({'img': f'http://127.0.0.1:8978/icon{i % 4}.jpeg',
                    'name': name, 'creator': f'Artist {i % 7}', 'time': 200 + i})
    return out


def page(path):
    """Tiny deterministic page for browser-history seeding. The browser treats
    inputs ending in .com as URLs, so seeds request /page/<n>.com."""
    m = re.match(r'/page/([\w-]+)', path)
    tag = m.group(1) if m else 'x'
    return (f'<!DOCTYPE html><html><head><title>OhmBench {tag}</title></head>'
            f'<body><h1>OhmBench {tag}</h1><p>seed page</p></body></html>')


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write('MOCK %s\n' % (fmt % a))

    def _send(self, body, ctype):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        try:
            if p.path.startswith('/feed'):
                return self._send(rss(p.path), 'application/xml')
            if p.path == '/search':
                kw = q.get('keyword', ['x'])[0]
                return self._send(__import__('json').dumps(songs(len(SONGS))), 'application/json')
            if p.path == '/randomSongs':
                return self._send(__import__('json').dumps(songs(q.get('count', ['27'])[0])), 'application/json')
            if p.path.startswith('/icon'):
                return self._send(ICON, 'image/jpeg')
            if p.path.startswith('/page/'):
                return self._send(page(p.path), 'text/html')
            if p.path.startswith('/media'):
                return self._send(__import__('json').dumps(songs(len(SONGS))), 'application/json')
        except Exception as e:
            self.send_error(500, str(e))
        self.send_error(404)


if __name__ == '__main__':
    HTTPServer(('127.0.0.1', 8978), H).serve_forever()
