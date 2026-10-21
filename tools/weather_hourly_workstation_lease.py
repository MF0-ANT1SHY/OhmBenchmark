"""Bounded ordinary ten-city forecast server; request receipts remain evaluator-side."""
import argparse,hashlib,json,os,threading
from urllib.parse import parse_qs,urlsplit,urlencode
from pathlib import Path
from http.server import ThreadingHTTPServer
from weather_hourly_data_service import handler,CITIES,forecast
from workstation_process import identity

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duration',type=int,default=7200);args=parser.parse_args()
    if not 60<=args.duration<=7200:raise ValueError('invalid service duration')
    base=Path(__file__).resolve().parent;lock=threading.Lock()
    def observe(path,start,end,status,body,sent,error,retrieved_at):
        url=urlsplit(path);query=parse_qs(url.query);query.pop('key',None);path=url.path+('?' + urlencode(query,doseq=True) if query else '')
        row={'path':path,'start':start,'end':end,'status':status,'body_sha256':hashlib.sha256(body).hexdigest(),'body_bytes':len(body),'sent_bytes':sent,'error':error,'retrieved_at':retrieved_at}
        with lock,(base/'requests.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(row)+'\n')
    server=ThreadingHTTPServer(('127.0.0.1',18496),handler(observe))
    source=base/'weather_hourly_data_service.py';launcher=Path(__file__).resolve()
    record={'pid':os.getpid(),'identity':identity(os.getpid()),'source':str(source),'daily_sha256':hashlib.sha256((base/'weather_session_data_service.py').read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'launcher':str(launcher),'launcher_sha256':hashlib.sha256(launcher.read_bytes()).hexdigest(),'catalogue_sha256':hashlib.sha256(json.dumps({c:forecast(c,'reference') for c in CITIES},sort_keys=True).encode()).hexdigest(),'base_url':'http://127.0.0.1:18496','hosting':'bounded foreground SSH lease'}
    (base/'process.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    timer=threading.Timer(args.duration,server.shutdown);timer.daemon=True;timer.start();print('Ordinary hourly forecast ready',flush=True)
    try:server.serve_forever()
    finally:timer.cancel();server.server_close()

if __name__=='__main__':main()
