import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from seed_classic_poems import generate


class PoemFixtureTests(unittest.TestCase):
    def test_ordinary_schema_contiguous_ids_and_readable_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=generate(Path(tmp)/'jingmo.db',100)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                columns={r[1] for r in db.execute('PRAGMA table_info(classicalliterature_classicpoem)')}
                self.assertEqual(columns,{'id','dynasty','writer','writer_introduction','title','subtitle','preface','content',
                    'annotation','translation','creative_background','explain','comment','collection','category'})
                rows=list(db.execute('SELECT id,title,content FROM classicalliterature_classicpoem ORDER BY id'))
                self.assertEqual([r[0] for r in rows],list(range(1,101)))
                self.assertTrue(all(r[1] and r[2] for r in rows))
                before=path.read_bytes()
            with self.assertRaises(FileExistsError):
                generate(path,200)
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':
    unittest.main()
