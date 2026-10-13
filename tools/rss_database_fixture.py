"""Check a normal reader database against the ordinary RSS catalogue."""
import hashlib
import json
import sqlite3
from pathlib import Path

from rss_data_service import Catalogue


def inspect(path):
    path = Path(path).resolve()
    catalogue = Catalogue('http://127.0.0.1:18491')
    expected_body = hashlib.sha256(catalogue.body.encode()).hexdigest()
    records = []
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('invalid reader database')
        feeds = db.execute('SELECT id,url,title FROM feeds ORDER BY id').fetchall()
        expected_urls = {f'{catalogue.base}/feeds/{i}.xml': i for i in range(1, 11)}
        if len(feeds) != 10 or {r[1] for r in feeds} != set(expected_urls):
            raise ValueError('reader database contains missing or unrelated subscriptions')
        for feed_id, url, title in feeds:
            number = expected_urls[url]
            if title != f'Journal {number}':
                raise ValueError('feed title differs from RSS data')
            rows = db.execute('SELECT title,link,author,guid,content FROM articles '
                              'WHERE feed_id=?', (feed_id,)).fetchall()
            expected_guids = {f'journal-{number}-{i}' for i in range(1, 101)}
            if len(rows) != 100 or {r[3] for r in rows} != expected_guids:
                raise ValueError('reader did not ingest exactly the expected articles')
            for article_title, link, author, guid, content in rows:
                article = int(guid.rsplit('-', 1)[1])
                body_hash = hashlib.sha256(content.encode()).hexdigest()
                if (article_title != f'Journal {number} article {article}'
                        or link != f'{catalogue.base}/articles/{number}/{article}.html'
                        or author != 'Reader' or body_hash != expected_body):
                    raise ValueError('stored article differs from ordinary RSS payload')
                records.append([url, article_title, link, author, guid, body_hash])
        if db.execute('SELECT COUNT(*) FROM articles').fetchone()[0] != 1000:
            raise ValueError('reader database contains unrelated article rows')
    semantic = hashlib.sha256(json.dumps(sorted(records), separators=(',', ':'),
                                        ensure_ascii=False).encode()).hexdigest()
    return {'database_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'semantic_sha256': semantic, 'feeds': 10, 'articles': 1000,
            'body_sha256': expected_body, 'integrity_check': 'ok',
            'functional_read_verified': True,
            'method': 'all normal feed URLs, article GUIDs, titles, links, authors and full bodies verified'}
