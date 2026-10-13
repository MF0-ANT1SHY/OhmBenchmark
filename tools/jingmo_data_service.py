#!/usr/bin/env python3
"""Ordinary poetry dataset responses for the reader's existing sync protocol."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit


class Catalogue:
    def __init__(self, count=5000):
        if type(count) is not int or not 1 <= count <= 100000:
            raise ValueError('positive bounded ordinary poem count required')
        self.poems = [
            {'id': i, 'dynasty': '今', 'writer': '佚名', 'writer_introduction': '',
             'title': f'山水诗 {i}', 'subtitle': '', 'preface': '',
             'content': '山影入清溪，微风送晚晴。归舟穿柳岸，远树映云青。',
             'annotation': '', 'translation': '', 'creative_background': '',
             'explain': '', 'comment': '', 'collection': '山水集', 'category': '山水'}
            for i in range(1, count + 1)]

    def response(self, path):
        if path == '/api/dataset_v2.json':
            data = [{'id': 1, 'name': '古诗词', 'count': len(self.poems), 'version': 1}]
        elif path == '/api/classicalliterature_classicpoem1.json':
            data = {'total': len(self.poems), 'data': self.poems, 'next_page': None}
        else:
            raise KeyError(path)
        return json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()


def handler(catalogue):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                payload = catalogue.response(urlsplit(self.path).path)
                status, mime = 200, 'application/json; charset=utf-8'
            except KeyError:
                payload, status, mime = b'Not found', 404, 'text/plain'
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18492)
    parser.add_argument('--count', type=int, default=5000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler(Catalogue(args.count)))
    print(f'Poetry source listening on {args.host}:{args.port}', flush=True)
    server.serve_forever()
