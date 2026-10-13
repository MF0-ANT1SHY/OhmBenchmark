#!/usr/bin/env python3
"""Build an ordinary Jingmo poetry database outside the application."""
import argparse
import sqlite3
from pathlib import Path


def generate(database, count):
    if count<1:
        raise ValueError('count must be positive')
    if database.exists():
        raise FileExistsError(database)
    database.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(database) as db:
        # Exact columns and constraints from the app's DbMigrationConst. No
        # counter columns, measurement metadata or alternative query functions.
        db.execute('CREATE TABLE classicalliterature_classicpoem ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, dynasty TEXT NOT NULL, writer TEXT NOT NULL,'
            'writer_introduction TEXT, title TEXT NOT NULL, subtitle TEXT, preface TEXT, content TEXT NOT NULL,'
            'annotation TEXT, translation TEXT, creative_background TEXT, explain TEXT, comment TEXT,'
            'collection TEXT, category TEXT)')
        db.executemany('INSERT INTO classicalliterature_classicpoem '
            '(dynasty,writer,writer_introduction,title,subtitle,preface,content,annotation,translation,'
            'creative_background,explain,comment,collection,category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (('今','佚名','',f'山水诗 {i}','','','山影入清溪，微风送晚晴。归舟穿柳岸，远树映云青。',
              '','','','','','山水集','山水') for i in range(1,count+1)))
        db.execute('PRAGMA user_version=1')
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('fixture database integrity failed')
    return database


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database',type=Path)
    parser.add_argument('--count',type=int,default=100000)
    args=parser.parse_args()
    print(generate(args.database,args.count))
