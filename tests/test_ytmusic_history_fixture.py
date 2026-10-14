import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from seed_ytmusic_history import preferences_bytes, seed
from install_ytmusic_history_fixture import fixture_state, other_preferences


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

    def test_archive_derivation_rechecked_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);template=base/'template.xml';template.write_bytes(self.template)
            catalogue=base/'songs.json';catalogue.write_text(json.dumps(self.songs))
            target=base/'fixture';seed(target,template,catalogue)
            self.assertEqual(fixture_state(target)[0]['songs'],1)
            path=target/'persistent_storage.xml';path.write_bytes(path.read_bytes().replace(b'Song A',b'Song B'))
            with self.assertRaises(ValueError):fixture_state(target)

    def test_other_preference_changes_are_not_hidden_by_history_replacement(self):
        prepared=preferences_bytes(self.template,self.songs)
        self.assertEqual(other_preferences(prepared),other_preferences(self.template))
        self.assertNotEqual(other_preferences(prepared),other_preferences(self.template.replace(b'unchanged',b'new-setting')))


if __name__ == '__main__':
    unittest.main()
