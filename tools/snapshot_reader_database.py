#!/usr/bin/env python3
"""Archive and verify an ordinarily populated reader database, outside the app."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid

from remote_device import Remote
from rss_database_fixture import inspect


def snapshot(remote, destination, dataset=None):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('refusing to overwrite an existing reader database snapshot')
    token = uuid.uuid4().hex
    device = f'/data/local/tmp/reader-database-{token}.db'
    archive = f'/home/research/ohm-clean/services/rss/snapshots/{token}.db'
    database = '/data/app/el2/100/database/com.sheafreader.hm/entry/rdb/sheaf_reader.db'
    code = """import hashlib,json,sqlite3,subprocess
from pathlib import Path
archive=Path(PAYLOAD['archive']).resolve();archive.parent.mkdir(parents=True,exist_ok=True)
try:
 p=subprocess.run(['hdc','shell',"sqlite3 "+PAYLOAD['database']+" '.backup "+PAYLOAD['device']+"'"],capture_output=True,text=True,timeout=90)
 assert p.returncode==0 and not p.stderr,p.stdout+p.stderr
 p=subprocess.run(['hdc','file','recv',PAYLOAD['device'],str(archive)],capture_output=True,text=True,timeout=180)
 assert p.returncode==0 and archive.is_file() and archive.stat().st_size>0,p.stdout+p.stderr
 with sqlite3.connect(archive.as_uri()+'?mode=ro',uri=True) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 print(json.dumps({'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
  'bytes':archive.stat().st_size,'remote_archive':str(archive),'database':PAYLOAD['database']}))
finally:
 subprocess.run(['hdc','shell','rm -f '+PAYLOAD['device']],capture_output=True,timeout=90)
"""
    receipt = json.loads(remote.python(code, {
        'archive': archive, 'device': device, 'database': database,
    }, timeout=300))
    remote.download(archive, destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != receipt['sha256']:
        raise RuntimeError('reader database snapshot transfer hash mismatch')
    receipt['ordinary_data'] = inspect(destination, dataset)
    receipt['performance_verified'] = False
    destination.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--remote', default='cityuPC')
    args = parser.parse_args()
    print(json.dumps(snapshot(Remote(args.remote), args.destination), indent=2))


if __name__ == '__main__':
    main()
