import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_wanharmony_history import seed,preferences_bytes
from install_wanharmony_history_fixture import fixture_state,install,other_preferences,verify_deployment,DEPLOYMENT

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

    def preparation(self):
        directory=self.root/'preparation';directory.mkdir()
        before=b'<preferences><string key="historyList">[]</string><string key="cookies">new-live-value</string><string key="new-setting">keep-me</string></preferences>'
        entries=json.loads(self.history.read_text());deployed=preferences_bytes(before,entries)
        (directory/'before.xml').write_bytes(before);(directory/'deployed.xml').write_bytes(deployed)
        prep={'deployment':DEPLOYMENT,'preparation_dir':str(directory),
              'before_sha256':hashlib.sha256(before).hexdigest(),'deployed_sha256':hashlib.sha256(deployed).hexdigest()}
        return prep,entries,directory

    def test_changed_live_settings_are_preserved_not_reverted_to_old_template(self):
        prep,entries,directory=self.preparation();fixture,_=fixture_state(self.fixture)
        self.assertEqual(verify_deployment(prep,entries,fixture),prep['deployed_sha256'])
        self.assertEqual(other_preferences((directory/'before.xml').read_bytes()),other_preferences((directory/'deployed.xml').read_bytes()))
        self.assertNotEqual(prep['deployed_sha256'],fixture['preferences_sha256'])

    def test_reverting_a_live_setting_is_rejected_even_with_a_matching_blob_hash(self):
        prep,entries,directory=self.preparation();fixture,_=fixture_state(self.fixture)
        blob=(directory/'deployed.xml').read_bytes().replace(b'new-live-value',b'old-value')
        (directory/'deployed.xml').write_bytes(blob);prep['deployed_sha256']=hashlib.sha256(blob).hexdigest()
        with self.assertRaisesRegex(ValueError,'unrelated preferences'):verify_deployment(prep,entries,fixture)

    def test_changed_baseline_or_history_cannot_reuse_preparation(self):
        prep,entries,directory=self.preparation();fixture,_=fixture_state(self.fixture)
        (directory/'before.xml').write_bytes((directory/'before.xml').read_bytes().replace(b'keep-me',b'changed'))
        with self.assertRaises(ValueError):verify_deployment(prep,entries,fixture)
