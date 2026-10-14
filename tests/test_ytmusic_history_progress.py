import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_ytmusic_history import preferences_bytes
from ytmusic_history_progress import BUNDLE, verify_layout, verify_state, verify_capture


class HistoryProgressTest(unittest.TestCase):
    def setUp(self):
        self.songs=[{'img':'https://example.org/cover.jpg','name':'Song A','creator':'Artist','time':312}]
        self.layout={'attributes':{'bundleName':BUNDLE,'type':'Column'},'children':[
            {'attributes':{'type':'Text','text':'历史记录'}},
            {'attributes':{'type':'Row'},'children':[
                {'attributes':{'type':'Column'},'children':[
                    {'attributes':{'type':'Text','text':'Song A'}},
                    {'attributes':{'type':'Text','text':'Artist'}}]}]}]}
        self.template=b'<preferences><string key="history">{"setReplacer":"_____set_replacer__","values":[]}</string></preferences>'

    def test_actual_name_creator_row_and_complete_native_history(self):
        self.assertEqual(verify_layout(self.layout,self.songs)['visible_songs'],[['Song A','Artist']])
        self.assertTrue(verify_state(preferences_bytes(self.template,self.songs),self.songs)['complete_history_preserved'])

    def test_header_only_other_app_wrong_creator_and_split_rows_rejected(self):
        for kind in ('header-only','other-app','wrong-creator','split-rows'):
            layout=copy.deepcopy(self.layout)
            if kind=='header-only':layout['children'].pop()
            if kind=='other-app':layout['attributes']['bundleName']='observer'
            if kind=='wrong-creator':layout['children'][1]['children'][0]['children'][1]['attributes']['text']='Wrong'
            if kind=='split-rows':
                column=layout['children'][1]['children'][0]
                column['children']=[{'attributes':{'type':'Row'},'children':[text]} for text in column['children']]
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify_layout(layout,self.songs)

    def test_native_storage_mutation_or_missing_catalogue_is_rejected(self):
        raw=preferences_bytes(self.template,self.songs)
        for altered in (raw.replace(b'Song A',b'Song B'),self.template):
            with self.assertRaises(ValueError):verify_state(altered,self.songs)

    def test_raw_ui_must_match_summary_inside_the_capture_window(self):
        observation={'layout':self.layout,'started_monotonic':2,'ended_monotonic':3,
                     'rows':verify_layout(self.layout,self.songs)}
        verify_capture(observation,self.songs,1,4)
        with self.assertRaises(ValueError):verify_capture(observation,self.songs,1,2.5)
        observation['rows']={}
        with self.assertRaises(ValueError):verify_capture(observation,self.songs,1,4)
