import copy
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_wanharmony_history import preferences_bytes,validate_entries

class WanHistoryFixtureTest(unittest.TestCase):
    def setUp(self):
        self.entries=[{'url':'https://example.com/article/1','title':'A & B','time':'2026/10/14 12:00:00','sticky':False}]
        self.template=b'<preferences><string key="historyList">[]</string><string key="theme">dark</string><int key="other" value="7"/></preferences>'
    def test_real_array_only_and_unrelated_settings_preserved(self):
        root=ET.fromstring(preferences_bytes(self.template,self.entries))
        self.assertEqual(json.loads(root[0].text),self.entries)
        original=ET.fromstring(self.template)
        self.assertEqual([ET.tostring(n) for n in root[1:]],[ET.tostring(n) for n in original[1:]])
    def test_rejects_annotations_duplicate_urls_and_bad_business_fields(self):
        for change in ({'counter':1},{'url':'file:///app/private'},{'url':'https://user:secret@example.com/a'},{'time':'2026/02/30 12:00:00'},{'time':'2026/1/1 00:00:00'},{'sticky':1},{'title':'x'*513}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_entries([{**self.entries[0],**change}])
        with self.assertRaises(ValueError):validate_entries(self.entries*2)
    def test_requires_initialized_native_array_not_a_guessed_marker(self):
        for template in (b'<preferences/>',b'<preferences><string name="historyList">[]</string></preferences>',b'<preferences><string key="historyList">{}</string></preferences>',b'<preferences><string key="historyList">[]</string><string key="historyList">[]</string></preferences>'):
            with self.subTest(template=template),self.assertRaises(ValueError):preferences_bytes(template,self.entries)
