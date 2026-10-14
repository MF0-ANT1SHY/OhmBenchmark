"""External ordinary cached data for the repeat-sync business scenario."""
import hashlib
import json
from pathlib import Path
import sqlite3

from install_sqlite_fixture import install
from jingmo_import_fixture import service, read_state, verify_state
from rss_service_fixture import same_instance

CASE = 'jingmo_sync_page_reimport'


def identity(database_hash, source_hash):
    return hashlib.sha256(json.dumps({'database': database_hash, 'data': source_hash},
                                      sort_keys=True).encode()).hexdigest()


def prepare(remote, case, database):
    if case['id'] != CASE or case['host_app']['bundle_name'] != 'com.hefengbao.jingmo.hw':
        raise ValueError('cached poetry data provided to a different business case')
    database = Path(database)
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute('SELECT * FROM classicalliterature_classicpoem ORDER BY id')]
    verify_state({'count': len(rows), 'raw_rows': json.dumps(rows)}, True)
    before_service = service(remote)
    installed = install(remote, case['host_app']['bundle_name'], case['testcase']['module'],
                        'jingmo.db', database)
    state = read_state(lambda command: remote.hdc(['shell', command]))
    verify_state(state, True)
    database_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    return {'sha256': identity(database_hash, before_service['sha256']),
            'database_sha256': database_hash, 'service': before_service,
            'installation': installed, 'before': state}


def finish(remote, before):
    after_service = service(remote)
    same_instance(before['service'], after_service)
    state = read_state(lambda command: remote.hdc(['shell', command]))
    verify_state(state, True)
    return {'sha256': before['sha256'], 'service': after_service, 'after': state}


def verify_preparation(before, after):
    verify_state(before['before'], True)
    verify_state(after['after'], True)
    same_instance(before['service'], after['service'])
    expected = identity(before['database_sha256'], before['service']['sha256'])
    if before['sha256'] != expected or after['sha256'] != expected:
        raise ValueError('cached poetry data identity changed')
