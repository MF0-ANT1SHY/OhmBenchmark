#!/usr/bin/env python3
"""Ordinary music API fixtures for the app's existing server-URL setting.

Runs outside the app. Unknown routes fail explicitly; there are no measurement,
status, synchronization or oracle endpoints exposed to the application.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class Catalogue:
    def __init__(self,count,base_url,artist_count=12):
        if count<1 or artist_count<1:raise ValueError('positive catalogue sizes required')
        self.cover=base_url.rstrip('/')+'/media/cover.svg'
        self.artists=[{'id':i+1,'name':f'Artist {i+1}'} for i in range(artist_count)]
        self.songs=[]
        for i in range(count):
            album={'id':1,'name':'Collection','picUrl':self.cover,'artists':self.artists,'size':count}
            self.songs.append({'id':i+1,'name':f'Track {i+1}','artists':self.artists,'album':album,
                'duration':60000,'alias':[],'fee':0,'ar':self.artists,'al':album,'dt':60000})
        self.playlist={'id':1,'name':'Collection','coverImgUrl':self.cover,'trackCount':count,
            'playCount':0,'subscribedCount':0,'subscribed':False,'userId':1,
            'creator':{'userId':1,'nickname':'Library','avatarUrl':self.cover},'description':'Music collection'}

    def response(self,path,query):
        if path=='/inner/version':return {'code':200}
        if path=='/personalized':return {'code':200,'result':[]}
        if path=='/search' and query.get('type',['1'])[0]=='1000':
            return {'code':200,'result':{'hasMore':False,'playlists':[self.playlist]}}
        if path in ('/search','/playlist/track/all'):
            try:
                offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['30'])[0])
            except ValueError:raise ValueError('invalid pagination')
            if offset<0 or not 1<=limit<=1000:raise ValueError('invalid pagination')
            songs=self.songs[offset:offset+limit]
            if path=='/playlist/track/all':return {'code':200,'songs':songs}
            return {'code':200,'result':{'songs':songs,'songCount':len(self.songs),'hasMore':offset+len(songs)<len(self.songs)}}
        if path=='/playlist/detail':return {'code':200,'playlist':self.playlist}
        raise KeyError(path)


def handler(catalogue):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            request=urlsplit(self.path)
            if request.path=='/media/cover.svg':
                payload=b'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#527d8e"/><circle cx="128" cy="128" r="72" fill="#d9ece7"/></svg>'
                status=200;mime='image/svg+xml'
            else:
                try:
                    value=catalogue.response(request.path,parse_qs(request.query))
                    status=200
                except KeyError:
                    value={'code':404,'message':'Unknown route'};status=404
                except ValueError:
                    value={'code':400,'message':'Invalid request'};status=400
                payload=json.dumps(value,ensure_ascii=False).encode();mime='application/json; charset=utf-8'
            self.send_response(status)
            self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(payload)))
            self.end_headers();self.wfile.write(payload)
    return Handler


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=18490)
    parser.add_argument('--count',type=int,default=10000)
    parser.add_argument('--base-url',default='http://127.0.0.1:18490',help='ordinary API URL visible to the app')
    args=parser.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),handler(Catalogue(args.count,args.base_url)))
    print(f'Music data service listening on {args.host}:{args.port}',flush=True)
    server.serve_forever()
