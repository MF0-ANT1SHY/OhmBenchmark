"""External ordinary data checks for a complete cold poetry import."""
import hashlib
import json
import time
from pathlib import Path

from jingmo_data_service import Catalogue
from install_sqlite_fixture import install
from rss_service_fixture import same_instance

CASE = 'jingmo_dataset_import_no_transaction'
ROOT = Path(__file__).resolve().parents[1]
DATABASE = '/data/app/el2/100/database/com.hefengbao.jingmo.hw/default/rdb/jingmo.db'


def service(remote):
    catalogue = Catalogue()
    paths = ('/api/dataset_v2.json', '/api/classicalliterature_classicpoem1.json')
    files = {path: hashlib.sha256(catalogue.response(path)).hexdigest() for path in paths}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    source_hash = hashlib.sha256((ROOT/'tools/jingmo_data_service.py').read_bytes()).hexdigest()
    code = """import json,hashlib,urllib.request
from pathlib import Path
record=json.loads(Path('/home/research/ohm-clean/services/jingmo/process.json').read_text())
proc=Path('/proc')/str(record['pid']);start=proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[19]
assert record['source'].encode() in proc.joinpath('cmdline').read_bytes()
assert hashlib.sha256(Path(record['source']).read_bytes()).hexdigest()==PAYLOAD['source_sha256']
assert record['base_url']=='http://127.0.0.1:18492/api/' and record['poems']==5000
for path,expected in PAYLOAD['files'].items():
 with urllib.request.urlopen('http://127.0.0.1:18492'+path,timeout=30) as response:
  assert response.status==200
  assert hashlib.sha256(response.read()).hexdigest()==expected
assert proc.joinpath('stat').read_text().rsplit(')',1)[1].split()[19]==start
print(json.dumps({'sha256':PAYLOAD['sha256'],'source_sha256':PAYLOAD['source_sha256'],
 'base_url':record['base_url'],'service_pid':record['pid'],'service_start_ticks':int(start),'files':PAYLOAD['files']}))
"""
    return json.loads(remote.python(code, {'files': files, 'sha256': digest,
                                          'source_sha256': source_hash}, timeout=120))


def read_state(shell):
    count = shell(f"sqlite3 {DATABASE} 'SELECT COUNT(*) FROM classicalliterature_classicpoem;'").strip()
    if not count.isdigit():
        raise ValueError('ordinary poetry database did not return a row count')
    raw = shell(f"sqlite3 -json {DATABASE} 'SELECT * FROM classicalliterature_classicpoem ORDER BY id;'")
    rows = json.loads(raw) if raw.strip() else []
    if len(rows) != int(count):
        raise ValueError('poetry data changed during its snapshot')
    return {'raw_rows': raw, 'count': int(count)}


def verify_state(state, imported):
    rows = json.loads(state['raw_rows']) if state['raw_rows'].strip() else []
    expected = Catalogue().poems if imported else []
    if rows != expected or state['count'] != len(expected):
        raise ValueError('ordinary poetry rows differ from the complete expected import state')


def complete_import(ui, timeout=180):
    deadline = time.monotonic() + timeout
    while True:
        count = ui.shell(f"sqlite3 {DATABASE} 'SELECT COUNT(*) FROM classicalliterature_classicpoem;'").strip()
        if count == '5000':
            state = read_state(ui.shell)
            verify_state(state, True)
            return state
        if not count.isdigit() or time.monotonic() >= deadline:
            raise ValueError('normal poetry import did not finish: '+count)
        time.sleep(.5)


def prepare(remote, case, empty_database):
    if case['id'] != CASE or case['host_app']['bundle_name'] != 'com.hefengbao.jingmo.hw':
        raise ValueError('cold poetry import data provided to a different case')
    import sqlite3
    with sqlite3.connect(Path(empty_database).resolve().as_uri()+'?mode=ro', uri=True) as db:
        if db.execute('SELECT COUNT(*) FROM classicalliterature_classicpoem').fetchone()[0] != 0:
            raise ValueError('cold import requires an empty ordinary database')
    before_service = service(remote)
    installed = install(remote, case['host_app']['bundle_name'], case['testcase']['module'],
                        'jingmo.db', empty_database)
    state = read_state(lambda command: remote.hdc(['shell', command]))
    verify_state(state, False)
    database_hash = hashlib.sha256(Path(empty_database).read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps({'database': database_hash, 'data': before_service['sha256']},
                                      sort_keys=True).encode()).hexdigest()
    return {'sha256': digest, 'database_sha256': database_hash, 'service': before_service,
            'installation': installed, 'before': state}


def finish(remote, before):
    after_service = service(remote)
    same_instance(before['service'], after_service)
    state = read_state(lambda command: remote.hdc(['shell', command]))
    verify_state(state, True)
    return {'service': after_service, 'after': state, 'sha256': before['sha256']}


def verify_preparation(before, after):
    verify_state(before['before'], False)
    verify_state(after['after'], True)
    same_instance(before['service'], after['service'])
    digest = hashlib.sha256(json.dumps({'database': before['database_sha256'],
        'data': before['service']['sha256']}, sort_keys=True).encode()).hexdigest()
    if digest != before['sha256'] or digest != after['sha256']:
        raise ValueError('poetry import data identity changed')
