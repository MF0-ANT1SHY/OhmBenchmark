import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from cloudmusic_data_service import Catalogue,handler


class MusicServiceTests(unittest.TestCase):
    def test_actual_http_pagination_and_unknown_routes(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(Catalogue(250,'http://127.0.0.1',3)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(url+'/playlist/track/all?offset=200&limit=100') as response:
                data=json.load(response)
            self.assertEqual(len(data['songs']),50)
            self.assertEqual(data['songs'][0]['id'],201)
            self.assertEqual(len(data['songs'][0]['ar']),3)
            with urlopen(url+'/search?type=1000') as response:data=json.load(response)
            self.assertEqual(data['result']['playlists'][0]['trackCount'],250)
            with self.assertRaises(HTTPError) as caught:urlopen(url+'/measurement-status')
            self.assertEqual(caught.exception.code,404)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
