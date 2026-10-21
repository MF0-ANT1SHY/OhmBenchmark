from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from music_search_progress import ARTISTS,BUNDLE,verify_capture

class MusicSearchProgressTests(unittest.TestCase):
    def record(self):
        return {'requests':[{'path':'/search?keywords=music&offset=0&limit=1000'}],'layout':{'attributes':{'bundleName':BUNDLE,'type':'List'},'children':[{'attributes':{'type':'Text','text':text,'visible':'true'}} for text in ('Track 1','Track 2',ARTISTS)]}}

    def test_first_page(self):self.assertEqual(verify_capture(self.record()),[1,2])

    def test_wrong_or_duplicate_page_request_rejected(self):
        for path in ('/search?keywords=other&offset=0&limit=1000','/search?keywords=music&offset=1000&limit=1000','/search?keywords=music&offset=0&limit=30'):
            r=self.record();r['requests'][0]['path']=path
            with self.assertRaises(ValueError):verify_capture(r)
        r=self.record();r['requests']*=2
        with self.assertRaises(ValueError):verify_capture(r)

    def test_wrong_rows_or_artists_rejected(self):
        for index,value in ((0,'Track 1001'),(2,'Wrong artist')):
            r=self.record();r['layout']['children'][index]['attributes']['text']=value
            with self.assertRaises(ValueError):verify_capture(r)

    def test_player_outside_search_list_is_not_a_result(self):
        r=self.record();r['layout']={'attributes':{'bundleName':BUNDLE},'children':[r['layout'],{'attributes':{'type':'Text','text':'Track 9999','visible':'true'}}]}
        self.assertEqual(verify_capture(r),[1,2])

    def test_pagination_boundaries_and_requests(self):
        from collect_music_search_pages import verify_pages
        raw={'layouts':{},'requests':[{'path':f'/search?keywords=music&offset={offset}&limit=1000'} for offset in (0,1000)]}
        for name,n in (('first',1),('page1_end',1000),('page2_start',1001),('page2_end',2000)):
            raw['layouts'][name]={'attributes':{'bundleName':BUNDLE,'type':'List'},'children':[{'attributes':{'type':'Text','text':t}} for t in (f'Track {n}',ARTISTS)]}
        verify_pages(raw)
        raw['requests'][1]['path']='/search?keywords=music&offset=30&limit=1000'
        with self.assertRaises(ValueError):verify_pages(raw)
