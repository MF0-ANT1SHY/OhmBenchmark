"""Ordinary four-day forecasts for the weather app's ten supported cities."""
import datetime,json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs,urlsplit
CITIES={'440300':'深圳市','440100':'广州市','310000':'上海市','110000':'北京市','320100':'南京市','420100':'武汉市','510100':'成都市','500000':'重庆市','610100':'西安市','410100':'郑州市'}

def forecast(code):
    city=CITIES[code];start=datetime.date(2026,10,21);casts=[];conditions=['晴','多云','阴','小雨']
    for day in range(4):
        date=start+datetime.timedelta(days=day)
        casts.append({'date':str(date),'week':date.isoweekday(),'dayweather':conditions[day],'nightweather':conditions[(day+1)%4],'daytemp':28-day,'nighttemp':23-day,'daywind':'东南','nightwind':'东南','daypower':'1-3','nightpower':'1-3','daytemp_float':float(28-day),'nighttemp_float':float(23-day)})
    return {'status':'1','count':1,'infocode':10000,'forecasts':[{'city':city,'adcode':int(code),'casts':casts}]}

def response(path):
    url=urlsplit(path);query=parse_qs(url.query)
    if url.path=='/v3/weather/weatherInfo' and query.get('extensions')==['all'] and len(query.get('city',[]))==1 and query['city'][0] in CITIES:
        return 200,json.dumps(forecast(query['city'][0]),ensure_ascii=False).encode()
    return 404,b'Not found'

def handler(observe):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            import time
            start=time.monotonic();status,body=response(self.path);sent=0;error=None
            try:
                self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body);self.wfile.flush();sent=len(body)
            except (BrokenPipeError,ConnectionResetError) as exc:error=type(exc).__name__
            finally:observe(self.path,start,time.monotonic(),status,body,sent,error)
    return Handler
