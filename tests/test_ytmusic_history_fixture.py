import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from seed_ytmusic_history import preferences_bytes


class HistoryFixtureTest(unittest.TestCase):
    def setUp(self):
        self.template = (b'<preferences><string key="history">'
                         b'{"setReplacer":"_____set_replacer__","values":[]}'
                         b'</string><string key="setting">unchanged</string></preferences>')
        self.songs = [{'img': 'https://example.org/cover.jpg', 'name': 'Song A',
                       'creator': 'Artist', 'time': 312}]

    def test_native_set_of_song_strings_and_other_preferences_preserved(self):
        root = ET.fromstring(preferences_bytes(self.template, self.songs))
        value = json.loads(root.find("string[@key='history']").text)
        self.assertEqual(value['setReplacer'], '_____set_replacer__')
        self.assertEqual([json.loads(item) for item in value['values']], self.songs)
        self.assertEqual(root.find("string[@key='setting']").text, 'unchanged')

    def test_nonproduction_fields_invalid_duration_and_duplicates_rejected(self):
        for songs in ([{**self.songs[0], 'counter': 1}], [{**self.songs[0], 'time': True}],
                      self.songs * 2, []):
            with self.subTest(songs=songs), self.assertRaises(ValueError):
                preferences_bytes(self.template, songs)

    def test_uninitialized_or_wrong_storage_representation_rejected(self):
        for template in (b'<preferences/>', self.template.replace(b'_____set_replacer__', b'invalid'),
                         self.template.replace(b'key="history"', b'key="different"')):
            with self.subTest(template=template), self.assertRaises(ValueError):
                preferences_bytes(template, self.songs)


if __name__ == '__main__':
    unittest.main()
