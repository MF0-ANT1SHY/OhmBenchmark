"""Bounded ordinary search server; request receipts remain evaluator-side."""
import argparse,hashlib,json,os,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from ytsearch_data_service import handler,CATALOGUE
from workstation_process import identity

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duration',type=int,default=7200);args=parser.parse_args()
    if not 60<=args.duration<=7200:raise ValueError('invalid service duration')
    base=Path(__file__).resolve().parent;lock=threading.Lock()
    def observe(path,start,end,status,body,sent,error):
        row={'path':path,'start':start,'end':end,'status':status,'body_sha256':hashlib.sha256(body).hexdigest(),'body_bytes':len(body),'sent_bytes':sent,'error':error}
        with lock,(base/'requests.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(row)+'\n')
    server=ThreadingHTTPServer(('127.0.0.1',18493),handler(observe))
    source=base/'ytsearch_data_service.py';launcher=Path(__file__).resolve()
    record={'pid':os.getpid(),'identity':identity(os.getpid()),'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'launcher':str(launcher),'launcher_sha256':hashlib.sha256(launcher.read_bytes()).hexdigest(),'catalogue_sha256':hashlib.sha256(json.dumps(CATALOGUE,sort_keys=True).encode()).hexdigest(),'base_url':'http://127.0.0.1:18493','hosting':'bounded foreground SSH lease'}
    (base/'process.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    timer=threading.Timer(args.duration,server.shutdown);timer.daemon=True;timer.start();print('Ordinary song search ready',flush=True)
    try:server.serve_forever()
    finally:timer.cancel();server.server_close()

if __name__=='__main__':main()
