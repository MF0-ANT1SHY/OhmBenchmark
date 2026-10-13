import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rss_data_service import Catalogue
from rss_database_fixture import inspect


class ReaderDatabaseFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.path = Path(cls.folder.name) / 'reader.db'
        cls.catalogue = Catalogue('http://127.0.0.1:18491')
        with sqlite3.connect(cls.path) as db:
            db.execute('CREATE TABLE feeds(id INTEGER PRIMARY KEY,url TEXT,title TEXT)')
            db.execute('CREATE TABLE articles(feed_id INTEGER,title TEXT,link TEXT,author TEXT,guid TEXT,content TEXT)')
            for number in range(1, 11):
                db.execute('INSERT INTO feeds VALUES(?,?,?)',
                           (number, f'{cls.catalogue.base}/feeds/{number}.xml', f'Journal {number}'))
                db.executemany('INSERT INTO articles VALUES(?,?,?,?,?,?)', [
                    (number, f'Journal {number} article {i}',
                     f'{cls.catalogue.base}/articles/{number}/{i}.html',
                     'Reader', f'journal-{number}-{i}', cls.catalogue.body)
                    for i in range(1, 101)])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_all_article_bodies_not_just_row_counts_are_checked(self):
        self.assertEqual(inspect(self.path)['articles'], 1000)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE articles SET content='wrong content' WHERE guid='journal-1-1'")
        try:
            with self.assertRaisesRegex(ValueError, 'stored article differs'):
                inspect(self.path)
        finally:
            with sqlite3.connect(self.path) as db:
                db.execute("UPDATE articles SET content=? WHERE guid='journal-1-1'", (self.catalogue.body,))

    def test_unrelated_subscriptions_are_not_valid_input(self):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO feeds VALUES(11,'https://example.org/old','Old subscription')")
        try:
            with self.assertRaisesRegex(ValueError, 'unrelated subscriptions'):
                inspect(self.path)
        finally:
            with sqlite3.connect(self.path) as db:
                db.execute('DELETE FROM feeds WHERE id=11')

    def test_equal_count_with_duplicate_guid_is_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE articles SET guid='journal-1-2' WHERE title='Journal 1 article 1'")
        try:
            with self.assertRaisesRegex(ValueError, 'expected articles'):
                inspect(self.path)
        finally:
            with sqlite3.connect(self.path) as db:
                db.execute("UPDATE articles SET guid='journal-1-1' WHERE title='Journal 1 article 1'")


if __name__ == '__main__':
    unittest.main()
