import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_search_history import production_states


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


if __name__=='__main__':unittest.main()
