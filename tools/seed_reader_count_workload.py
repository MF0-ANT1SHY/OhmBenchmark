#!/usr/bin/env python3
"""Create ordinary subscriptions/articles for a large unread-count workload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time


def seed(template, destination, fetched_ms, feeds=100, articles=1000):
    destination=Path(destination)
    if destination.exists() or type(fetched_ms) is not int or fetched_ms <= 0:
        raise ValueError('new destination and positive device-clock timestamp required')
    if not 10 <= feeds <= 1000 or not 10 <= articles <= 10000:
        raise ValueError('unsupported ordinary dataset size')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template,destination)
    with sqlite3.connect(destination) as db:
        db.row_factory=sqlite3.Row
        feed=dict(db.execute('SELECT * FROM feeds LIMIT 1').fetchone())
        article=dict(db.execute('SELECT * FROM articles LIMIT 1').fetchone())
        db.execute('DELETE FROM articles');db.execute('DELETE FROM feeds')
        columns=list(feed);sql='INSERT INTO feeds ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')'
        expected={}
        for number in range(1,feeds+1):
            row={**feed,'id':number,'url':f'http://127.0.0.1:18491/feeds/{number}.xml',
                 'title':f'Journal {number}','fetch_frequency':60,'last_fetched':fetched_ms,'sort_order':number}
            db.execute(sql,[row[k] for k in columns])
            expected[number]=0 if number==feeds else min(articles,(number%10+1)*articles//10)
        columns=list(article);sql='INSERT INTO articles ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')'
        def records():
            for number in range(1,feeds+1):
                for item in range(1,articles+1):
                    row={**article,'id':(number-1)*articles+item,'feed_id':number,
                         'title':f'Journal {number} article {item}',
                         'link':f'http://127.0.0.1:18491/articles/{number}/{item}.html',
                         'guid':f'journal-{number}-{item}','fetched':fetched_ms,
                         'read':int(item>expected[number])}
                    yield [row[k] for k in columns]
        db.executemany(sql,records())
        for key,value in {'menu_on':'1','fetch_interval':'0','unread_sources_only':'0'}.items():
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)',(key,value))
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        grouped=dict(db.execute('SELECT feed_id,COUNT(*) FROM articles WHERE read=0 GROUP BY feed_id'))
        individual={i:db.execute('SELECT COUNT(*) FROM articles WHERE read=0 AND feed_id=?',(i,)).fetchone()[0] for i in expected}
        assert individual==expected and all(grouped.get(i,0)==n for i,n in expected.items())
        plan=[tuple(r) for r in db.execute('EXPLAIN QUERY PLAN SELECT COUNT(*) FROM articles WHERE read=0 AND feed_id=1')]
        db.commit()
    proof={'feeds':feeds,'articles_per_feed':articles,'articles':feeds*articles,'device_fetched_ms':fetched_ms,
           'fetch_frequency_minutes':60,'expected_counts':expected,'both_query_results_equal':True,
           'host_query_plan':plan,'database_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
           'method':'Ordinary native tables and settings; no app markers or counters. Recent successful-fetch timestamps keep network refresh outside this workload.'}
    destination.with_suffix('.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('template',type=Path);p.add_argument('destination',type=Path)
    p.add_argument('--fetched-ms',type=int,required=True);p.add_argument('--feeds',type=int,default=100);p.add_argument('--articles',type=int,default=1000)
    a=p.parse_args();print(json.dumps(seed(a.template,a.destination,a.fetched_ms,a.feeds,a.articles),indent=2))
