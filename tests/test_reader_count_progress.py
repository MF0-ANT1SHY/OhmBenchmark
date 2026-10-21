import copy
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reader_count_progress import database_identity,visible_badges,BUNDLE


def text(value):return {'attributes':{'type':'Text','text':value,'visible':'true'}}
def layout():
    return {'attributes':{'bundleName':BUNDLE},'children':[
        {'attributes':{'type':'Row','visible':'true'},'children':[text(f'Journal {i}'),text(str(i*10))]}
        for i in range(1,6)]}


class CountProgressTests(unittest.TestCase):
    def test_badges_match_and_article_footer_is_not_badge(self):
        value=layout();value['children'].append({'attributes':{'type':'Row'},'children':[text('Journal 1'),text('20d')]})
        expected={f'Journal {i}':i*10 for i in range(1,6)}
        self.assertEqual(visible_badges(value,expected),expected)

    def test_incomplete_wrong_or_duplicate_badges_rejected(self):
        expected={f'Journal {i}':i*10 for i in range(1,6)}
        variants=[layout(),layout(),layout()]
        variants[0]['children'].pop()
        variants[1]['children'][0]['children'][1]=text('999')
        variants[2]['children'].append(copy.deepcopy(variants[2]['children'][0]))
        for value in variants:
            with self.assertRaises(ValueError):visible_badges(value,expected)

    def test_full_content_detects_changes_even_when_counts_equal(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'data.db'
            with sqlite3.connect(p) as db:
                db.executescript('CREATE TABLE feeds(id INTEGER,title TEXT); CREATE TABLE articles(id INTEGER,feed_id INTEGER,read INTEGER); INSERT INTO feeds VALUES(1,"Journal 1"); INSERT INTO articles VALUES(1,1,0),(2,1,1);')
            before=database_identity(p)
            with sqlite3.connect(p) as db:db.execute('UPDATE articles SET read=1-read')
            after=database_identity(p)
            self.assertEqual(before['counts'],after['counts'])
            self.assertNotEqual(before['articles']['sha256'],after['articles']['sha256'])

    def test_clipped_row_is_not_complete_badge_evidence(self):
        value=layout();expected={f'Journal {i}':i*10 for i in range(1,7)}
        value['children'].append({'attributes':{'type':'Row','visible':'true','bounds':'[0,333][945,377]','origBounds':'[0,242][945,377]'},'children':[text('Journal 6')]})
        self.assertEqual(set(visible_badges(value,expected,fully_visible=True)),set(expected)-{'Journal 6'})
        value['children'][-1]['attributes']['origBounds']='[0,333][945,377]'
        with self.assertRaises(ValueError):visible_badges(value,expected,fully_visible=True)
