import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from reader_unread_badges import BUNDLE, verify_layout


class UnreadBadgeTest(unittest.TestCase):
    def layout(self):
        return {'attributes': {'bundleName': BUNDLE}, 'children': [
            {'attributes': {'type': 'Row'}, 'children': [
                {'attributes': {'type': 'Text', 'text': f'Journal {i}'}},
                {'attributes': {'type': 'Text', 'text': '100'}}]} for i in range(1, 11)]}

    def test_same_row_badges_match_all_ordinary_feeds(self):
        self.assertEqual(verify_layout(self.layout()), {f'Journal {i}': 100 for i in range(1, 11)})

    def test_article_feed_labels_and_ages_are_not_sidebar_badges(self):
        layout=self.layout()
        footer={'attributes':{'type':'Row'},'children':[
            {'attributes':{'type':'Text','text':'Journal 1'}},
            {'attributes':{'type':'Text','text':'13d'}}]}
        card={'attributes':{'type':'Row'},'children':[
            {'attributes':{'type':'Column'},'children':[footer]}]}
        layout['children'].insert(0,card)
        self.assertEqual(verify_layout(layout),{f'Journal {i}':100 for i in range(1,11)})
        with self.assertRaises(ValueError):verify_layout({'attributes':{'bundleName':BUNDLE},'children':[card]})

    def test_missing_wrong_duplicate_and_other_app_badges_rejected(self):
        for change in ('missing', 'wrong', 'duplicate', 'other-app'):
            layout = self.layout()
            if change == 'missing': layout['children'].pop()
            if change == 'wrong': layout['children'][0]['children'][1]['attributes']['text'] = '0'
            if change == 'duplicate': layout['children'].append(copy.deepcopy(layout['children'][0]))
            if change == 'other-app': layout['attributes']['bundleName'] = 'observer'
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_layout(layout)


if __name__ == '__main__':
    unittest.main()
