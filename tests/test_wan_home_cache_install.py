import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_wan_home_cache import seed
from install_wan_home_cache_fixture import fixture_state,install,other_preferences
class WanHomeCacheInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.template=self.root/'template.xml';self.template.write_bytes(b'<preferences><string key="homeList">[]</string><string key="homeListCache">[]</string><string key="historyList">[]</string></preferences>')
        self.page=self.root/'page.json';self.page.write_text(json.dumps({'errorCode':0,'data':{'datas':[{'id':i+1,'title':f'Article {i}','desc':'','chapterName':'News','link':f'https://example.com/{i}'} for i in range(40)]}}))
        self.folder=self.root/'fixture';seed(self.folder,self.template,[self.page])
    def test_published_input_derivation_and_unrelated_history_preserved(self):
        r,b=fixture_state(self.folder);self.assertEqual(r['articles'],40)
        self.assertEqual(other_preferences(b),other_preferences(self.template.read_bytes()))
    def test_changed_api_source_or_cache_bytes_are_rejected(self):
        self.page.write_text(self.page.read_text().replace('News','Changed'))
        with self.assertRaises(ValueError):fixture_state(self.folder)
    def test_wrong_case_cannot_mutate_device(self):
        case={'id':'wanharmony_history_log_materialization','host_app':{'bundle_name':'org.example.wan.ohos'}}
        with self.assertRaises(ValueError):install(None,case,self.folder,'/data/app/el2/100/base/org.example.wan.ohos/haps/entry/files/persistent_storage')
