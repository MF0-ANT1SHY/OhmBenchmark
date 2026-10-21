import hashlib
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from weather_data_service import forecast,handler

class WeatherFixtureTests(unittest.TestCase):
    def test_forecasts_match_consumed_model(self):
        for code,city in (('440300','深圳市'),('440100','广州市')):
            result=forecast(code);self.assertEqual(result['status'],'1');self.assertEqual(result['forecasts'][0]['city'],city)
            days=result['forecasts'][0]['casts'];self.assertEqual(len(days),4);self.assertEqual(len({d['date'] for d in days}),4)
            self.assertEqual({d['dayweather'] for d in days},{'晴','多云','阴','小雨'})

    def test_icon_response_preserves_exact_bytes_and_unknown_routes_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);payload=b'\x89PNG\r\n\x1a\nfixture-image-bytes';(p/'sunny.img').write_bytes(payload)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(p,0));worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                with urlopen(base+'/weather/sunny.img') as response:self.assertEqual(response.read(),payload);self.assertEqual(response.headers['Content-Type'],'image/png')
                with self.assertRaises(HTTPError) as error:urlopen(base+'/status')
                self.assertEqual(error.exception.code,404)
            finally:server.shutdown();server.server_close();worker.join()
