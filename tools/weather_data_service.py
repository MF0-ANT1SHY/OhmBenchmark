"""Ordinary deterministic forecast and identical icon responses for native trials."""
import argparse
import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import time
from urllib.parse import parse_qs,urlsplit

CITIES={'440300':'深圳市','440100':'广州市','110000':'北京市','310000':'上海市'}

def forecast(code):
    city=CITIES[code];start=datetime.date(2026,10,21);casts=[]
    conditions=['晴','多云','阴','小雨']
    for day in range(4):
        date=start+datetime.timedelta(days=day)
        casts.append({'date':str(date),'week':date.isoweekday(),'dayweather':conditions[day],'nightweather':conditions[(day+1)%4],'daytemp':28-day,'nighttemp':23-day,'daywind':'东南','nightwind':'东南','daypower':'1-3','nightpower':'1-3','daytemp_float':float(28-day),'nighttemp_float':float(23-day)})
    return {'status':'1','count':1,'infocode':10000,'forecasts':[{'city':city,'adcode':int(code),'casts':casts}]}

def handler(icons,delay):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            url=urlsplit(self.path);query=parse_qs(url.query);status=200
            if url.path=='/v3/weather/weatherInfo' and query.get('city',[''])[0] in CITIES:
                content=json.dumps(forecast(query['city'][0]),ensure_ascii=False).encode();mime='application/json; charset=utf-8'
            elif url.path in ['/weather/'+name+'.img' for name in ('sunny','cloudy','overcast','rain')]:
                content=(icons/url.path.rsplit('/',1)[-1]).read_bytes();mime='image/png';time.sleep(delay)
            else:content=b'Not found';mime='text/plain';status=404
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
    return Handler

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--icons',type=Path,required=True);p.add_argument('--delay',type=float,default=4.0);a=p.parse_args()
    if not 0<=a.delay<=5:raise ValueError('invalid declared icon response delay')
    ThreadingHTTPServer(('127.0.0.1',18492),handler(a.icons,a.delay)).serve_forever()
