import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_wanharmony_history import seed
from install_wanharmony_history_fixture import fixture_state,install,other_preferences

class WanHistoryInstallTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.template=self.root/'initialized.xml';self.template.write_bytes(b'<preferences><string key="historyList">[]</string><string key="cookies">unchanged</string></preferences>')
        self.history=self.root/'history.json';self.history.write_text(json.dumps([{'url':'https://example.com/a','title':'Article','time':'2026/10/14 12:00:00','sticky':False}]))
        self.fixture=self.root/'fixture';seed(self.fixture,self.template,self.history)
    def test_exact_fixture_derivation_and_other_keys_preserved(self):
        r,b=fixture_state(self.fixture);self.assertEqual(r['entries'],1)
        self.assertEqual(other_preferences(b),other_preferences(self.template.read_bytes()))
    def test_tampered_bytes_or_fields_rejected(self):
        p=self.fixture/'history.json';x=json.loads(p.read_text());x[0]['counter']=1;p.write_text(json.dumps(x))
        with self.assertRaises(ValueError):fixture_state(self.fixture)
    def test_wrong_app_or_native_path_rejected_before_remote_actions(self):
        case={'id':'wanharmony_history_log_materialization','host_app':{'bundle_name':'org.example.wan.ohos'}}
        for modified,path in [({**case,'id':'another'},'/data/app/el2/100/base/org.example.wan.ohos/haps/entry/files/persistent_storage'),(case,'/data/app/el2/100/base/another/files/persistent_storage'),(case,'/data/local/tmp/persistent_storage')]:
            with self.subTest(path=path),self.assertRaises(ValueError):install(None,modified,self.fixture,path)
