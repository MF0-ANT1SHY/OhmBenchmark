import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from wan_home_write_cycle import verify_backend_page


class PublicPageTest(unittest.TestCase):
    def page(self,count=8):
        return {'errorCode':0,'data':{'curPage':5,'size':10,'datas':[
            {'id':i+1,'title':'A &amp; B','chapterName':'public','desc':''} for i in range(count)]}}

    def test_actual_short_successful_page_is_retained_without_padding(self):
        rows=verify_backend_page(self.page(),4)
        self.assertEqual(len(rows),8)
        self.assertEqual(rows[0]['title'],'A & B')
        self.assertEqual(len(verify_backend_page(self.page(10),4)),10)

    def test_failed_wrong_page_wrong_request_size_and_duplicate_rows_rejected(self):
        bad=[self.page(0),self.page(11)]
        for key,value in (('curPage',4),('size',20)):
            p=self.page();p['data'][key]=value;bad.append(p)
        p=self.page();p['errorCode']=-1;bad.append(p)
        p=self.page();p['data']['datas'][1]=copy.deepcopy(p['data']['datas'][0]);bad.append(p)
        for p in bad:
            with self.assertRaises(ValueError):verify_backend_page(p,4)
