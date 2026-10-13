import json
import sys
import unittest
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_search_history import production_states,seed
from install_search_history_fixture import fixture_state,install


def read(blob):
    root=ET.fromstring(blob)
    assert root.tag=='preferences'
    return {node.attrib['key']:node.text for node in root}


class HistoryFixtureTest(unittest.TestCase):
    def test_same_events_produce_unbounded_and_capped_production_states(self):
        words=[f'面试题 {i}' for i in range(60)]
        states=production_states(words)
        self.assertEqual(read(states['unfixed']),dict(zip(words,words)))
        self.assertEqual(json.loads(read(states['fixed'])['keywords']),list(reversed(words[-20:])))

    def test_repeated_search_moves_recent_item_without_duplicates(self):
        states=production_states(['A','B','A'])
        self.assertEqual(read(states['unfixed']),{'A':'A','B':'B'})
        self.assertEqual(json.loads(read(states['fixed'])['keywords']),['A','B'])

    def test_native_key_attribute_and_xml_escaping(self):
        words=['问题 <A&B> "中文"']
        states=production_states(words)
        self.assertEqual(read(states['unfixed']),{words[0]:words[0]})
        self.assertNotIn(b'name=',states['unfixed'])
        self.assertEqual(json.loads(read(states['fixed'])['keywords']),words)

    def test_tampered_xml_is_rejected_even_if_its_manifest_hash_is_updated(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'fixture'
            seed(folder,60)
            receipt,blob=fixture_state(folder,'fixed')
            altered=blob.replace('面试题 59'.encode(),'伪造关键词'.encode())
            (folder/'fixed.xml').write_bytes(altered)
            receipt['variants']['fixed']['sha256']=hashlib.sha256(altered).hexdigest()
            (folder/'fixture.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'production state'):
                fixture_state(folder,'fixed')

    def test_wrong_app_preference_path_is_rejected_before_device_access(self):
        class Remote:
            def hdc(self,args):raise AssertionError('must not touch the device')
        case={'id':'interviewapp_search_history_unbounded','host_app':{'bundle_name':'com.itcast.pass_interview'}}
        with self.assertRaisesRegex(ValueError,'initialized app history'):
            install(Remote(),case,'fixed',Path('/unused'),'/data/app/el2/100/base/other/preferences/historyStore')


if __name__=='__main__':unittest.main()
