"""Host the ordinary music catalogue during a bounded workstation lease."""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from cloudmusic_data_service import Catalogue,handler
from workstation_process import identity


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--duration',type=int,default=7200)
    a=p.parse_args()
    if not 60<=a.duration<=7200:raise ValueError('invalid service lease')
    base=Path(__file__).resolve().parent;catalogue=Catalogue(10000,'http://127.0.0.1:18490',12)
    ordinary=handler(catalogue);lock=threading.Lock()
    class Handler(ordinary):
        def do_GET(self):
            start=time.monotonic()
            try:super().do_GET()
            finally:
                with lock,(base/'requests.jsonl').open('a',encoding='utf8') as f:
                    f.write(json.dumps({'path':self.path,'start':start,'end':time.monotonic()})+'\n')
    server=ThreadingHTTPServer(('127.0.0.1',18490),Handler)
    source=base/'cloudmusic_data_service.py';launcher=Path(__file__).resolve()
    record={'pid':os.getpid(),'source':str(source),'launcher':str(launcher),'launcher_sha256':hashlib.sha256(launcher.read_bytes()).hexdigest(),'base_url':'http://127.0.0.1:18490','count':10000,'identity':identity(os.getpid()),'hosting':'bounded foreground SSH lease'}
    (base/'process.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    timer=threading.Timer(a.duration,server.shutdown);timer.daemon=True;timer.start()
    print('Owned music catalogue ready',flush=True)
    try:server.serve_forever()
    finally:timer.cancel();server.server_close()

if __name__=='__main__':main()
