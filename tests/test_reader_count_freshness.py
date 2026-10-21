from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from accept_reader_count_evidence import verify_recent_input


class RecentCountInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'native.db'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE feeds(last_fetched INTEGER,fetch_frequency INTEGER)')
            db.executemany('INSERT INTO feeds VALUES (?,?)',[(1000,60)]*100)
        self.record={'seed_fetched_ms':1000,'device_clock_before_ms':2000,'device_clock_after_ms':3000,
                     'reader_fixture_before':{'snapshot':{'local_database':str(self.path)}}}

    def test_recent_native_limits_pass(self):verify_recent_input(self.record)

    def test_future_seed_or_expiry_during_trial_rejected(self):
        for changes in ({'device_clock_before_ms':999},{'device_clock_after_ms':3601000}):
            with self.assertRaises(ValueError):verify_recent_input({**self.record,**changes})

    def test_unlimited_native_feed_rejected(self):
        with sqlite3.connect(self.path) as db:db.execute('UPDATE feeds SET fetch_frequency=0 WHERE rowid=1')
        with self.assertRaises(ValueError):verify_recent_input(self.record)

    def test_missing_subscription_rejected(self):
        with sqlite3.connect(self.path) as db:db.execute('DELETE FROM feeds WHERE rowid=1')
        with self.assertRaises(ValueError):verify_recent_input(self.record)
