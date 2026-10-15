import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_wan_home_primary import network_progress,paired_viewports,cache,BUNDLE

class WanHomePrimaryProgressTest(unittest.TestCase):
    def line(self,time,message,pid=20,level='I'):
        return f'{time}.000000001 {pid} 21 {level} domain/{BUNDLE}/network: {message}'
    def logs(self):
        lines=[]
        for i in range(1,4):
            lines.append(self.line(100+i*2,f'get: https://www.wanandroid.com/article/list/{i}/json?page={i}&page_size=10'))
            lines.append(self.line(101+i*2,'(200) response: {"data":{"curPage":'+str(i+1)+',"datas":[{"id":1'))
        return '\n'.join(lines)
    def test_normal_sequential_page_progress_is_not_replaced_by_ui_presence(self):
        self.assertEqual(network_progress('',self.logs(),20)['requested_pages'],[1,2,3])
        for logs in ('',self.logs().replace('"curPage":4','"curPage":5'),self.logs().replace('page=2&','page=9&'),self.logs()+'\n'+self.line(120,'err = (1) network failure',level='E'),self.logs().replace(' 20 21 ',' 99 21 ')):
            with self.assertRaises(ValueError):network_progress('',logs,20)
        with self.assertRaises(ValueError):network_progress(self.logs(),self.logs(),20)
    def layout(self,indices):
        return {'attributes':{'bundleName':BUNDLE},'children':[{'attributes':{'text':'Article '+str(i)}} for i in indices]}
    def test_original_swipes_allow_real_scroll_offset_difference_but_not_different_loaded_pages(self):
        articles=[{'id':i+1,'title':'Article '+str(i)} for i in range(40)]
        result=paired_viewports(self.layout(range(30,35)),self.layout(range(28,33)),articles)
        self.assertFalse(result['identical']);self.assertEqual([i for i,_ in result['shared']],[30,31,32])
        with self.assertRaises(ValueError):paired_viewports(self.layout(range(30,35)),self.layout(range(10,15)),articles)
        foreign=self.layout(range(30,35));foreign['attributes']['bundleName']='other'
        with self.assertRaises(ValueError):paired_viewports(self.layout(range(30,35)),foreign,articles)
    def test_duplicate_or_nonbusiness_cache_rows_do_not_prove_input_identity(self):
        for raw in ('<preferences />','<preferences><string key="homeList">[1]</string></preferences>','<preferences><string key="homeList">[{"id":1},{"id":1}]</string></preferences>'):
            with self.assertRaises(ValueError):cache(raw,'homeList')
