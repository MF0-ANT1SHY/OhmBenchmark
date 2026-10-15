import json,sys,tempfile,unittest
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_wan_home_cache import catalogue,preferences_bytes
class WanHomeCacheTest(unittest.TestCase):
    def setUp(self):
        self.articles=[{'id':i+1,'title':f'Article {i}','desc':'','chapterName':'News','link':f'https://example.com/{i}'} for i in range(40)]
        self.template=b'<preferences><string key="homeList">[]</string><string key="homeListCache">[]</string><string key="cookies">unchanged</string></preferences>'
    def test_two_real_business_keys_same_file_unrelated_preferences_unchanged(self):
        root=ET.fromstring(preferences_bytes(self.template,self.articles))
        self.assertEqual(json.loads(root[0].text),self.articles);self.assertEqual(json.loads(root[1].text),self.articles[:20])
        self.assertEqual(ET.tostring(root[2]),ET.tostring(ET.fromstring(self.template)[2]))
    def test_missing_or_guessed_native_format_rejected(self):
        for t in [b'<preferences/>',self.template.replace(b'[]',b'{}')]:
            with self.assertRaises(ValueError):preferences_bytes(t,self.articles)
    def test_real_api_derivation_and_id_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'page.json';p.write_text(json.dumps({'errorCode':0,'data':{'datas':self.articles+self.articles[:1]}}))
            rows,sources=catalogue([p]);self.assertEqual(rows,self.articles);self.assertEqual(len(sources),1)
            p.write_text(json.dumps({'errorCode':-1,'data':{'datas':self.articles}}))
            with self.assertRaises(ValueError):catalogue([p])

class WanHomeDeploymentTest(unittest.TestCase):
    setUp=WanHomeCacheTest.setUp
    def test_current_cookies_and_history_are_preserved_not_replaced_by_old_template(self):
        from install_wan_home_cache_fixture import other_preferences
        before=self.template.replace(b'unchanged',b'new-live-cookie').replace(b'</preferences>',b'<string key="historyList">[{"title":"visited"}]</string></preferences>')
        deployed=preferences_bytes(before,self.articles)
        self.assertEqual(other_preferences(before),other_preferences(deployed))
        self.assertIn(b'new-live-cookie',deployed)
        self.assertIn(b'visited',deployed)

    def test_deployment_rejects_unrelated_mutation_even_with_updated_output_hash(self):
        import hashlib
        from install_wan_home_cache_fixture import verify_deployment,DEPLOYMENT
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);before=self.template;deployed=preferences_bytes(before,self.articles)
            (directory/'before.xml').write_bytes(before);(directory/'deployed.xml').write_bytes(deployed)
            preparation={'deployment':DEPLOYMENT,'preparation_dir':str(directory),'before_sha256':hashlib.sha256(before).hexdigest(),'deployed_sha256':hashlib.sha256(deployed).hexdigest()}
            self.assertEqual(verify_deployment(preparation,self.articles,{}),preparation['deployed_sha256'])
            changed=deployed.replace(b'unchanged',b'tampered');(directory/'deployed.xml').write_bytes(changed);preparation['deployed_sha256']=hashlib.sha256(changed).hexdigest()
            with self.assertRaises(ValueError):verify_deployment(preparation,self.articles,{})
            preparation['deployment']='unrecognized'
            with self.assertRaises(ValueError):verify_deployment(preparation,self.articles,{})

    def test_historical_exact_template_receipts_remain_distinct(self):
        from install_wan_home_cache_fixture import verify_deployment
        self.assertEqual(verify_deployment({},self.articles,{'preferences_sha256':'historical'}),'historical')
