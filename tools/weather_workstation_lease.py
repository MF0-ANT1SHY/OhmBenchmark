"""Bounded ordinary forecast/icon service with external request receipts."""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs,urlsplit,urlencode
from weather_data_service import CITIES,forecast,handler
from workstation_process import identity


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--duration',type=int,default=7200);p.add_argument('--delay',type=float,default=4.0);a=p.parse_args()
    if not 60<=a.duration<=7200 or not 0<=a.delay<=5:raise ValueError('invalid declared service bounds')
    base=Path(__file__).resolve().parent;icons=base/'ordinary-icons';ordinary=handler(icons,a.delay);lock=threading.Lock()
    class Handler(ordinary):
        def do_GET(self):
            start=time.monotonic();path=urlsplit(self.path);query=parse_qs(path.query)
            # Provider credentials are neither needed nor retained in observer logs.
            query.pop('key',None);safe_path=path.path+('?' + urlencode(query,doseq=True) if query else '')
            try:super().do_GET()
            finally:
                with lock,(base/'requests.jsonl').open('a',encoding='utf8') as f:
                    f.write(json.dumps({'path':safe_path,'start':start,'end':time.monotonic()})+'\n')
    server=ThreadingHTTPServer(('127.0.0.1',18492),Handler)
    source=base/'weather_data_service.py';launcher=Path(__file__).resolve()
    record={'pid':os.getpid(),'identity':identity(os.getpid()),'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'launcher':str(launcher),'launcher_sha256':hashlib.sha256(launcher.read_bytes()).hexdigest(),'icon_delay_s':a.delay,'base_url':'http://127.0.0.1:18492','icons_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in icons.iterdir()},'forecasts_sha256':hashlib.sha256(json.dumps({c:forecast(c) for c in CITIES},ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'hosting':'bounded foreground SSH lease'}
    (base/'process.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    timer=threading.Timer(a.duration,server.shutdown);timer.daemon=True;timer.start();print('Owned ordinary weather source ready',flush=True)
    try:server.serve_forever()
    finally:timer.cancel();server.server_close()

if __name__=='__main__':main()
