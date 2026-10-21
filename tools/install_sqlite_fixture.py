#!/usr/bin/env python3
"""Install an offline SQLite fixture into a stopped app, preserving its owner.

Requires a root-capable test device. Existing data is backed up on the evaluator
workstation before replacement. No measurement files or code enter the HAP.
"""
import argparse
import gzip
import hashlib
import json
import re
import shlex
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from remote_device import Remote


def install(remote, bundle, module, database, fixture):
    for value in (bundle, module, database):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("invalid app/database identifier")
    stamp = str(time.time_ns())
    device_db = f"/data/app/el2/100/database/{bundle}/{module}/rdb/{database}"
    host_base = f"/home/research/ohm-clean/fixtures/{stamp}"
    backup = f"/home/research/ohm-clean/backups/{bundle}/{stamp}/{database}"
    remote.hdc(["shell", f"aa force-stop {bundle}"])
    output = remote.hdc(["shell", f"ls -ln {device_db}"])
    fields = output.split()
    if len(fields) < 5 or not fields[2].isdigit() or not fields[3].isdigit():
        raise RuntimeError(f"database not initialized: {output}")
    uid, gid = fields[2:4]
    device_backup = f"/data/local/tmp/workload-backup-{stamp}.db"
    remote.hdc(["shell", f"sqlite3 {device_db} 'PRAGMA wal_checkpoint(TRUNCATE);'"])
    remote.hdc(["shell", f"sqlite3 {device_db} '.backup {device_backup}'"])
    remote.python("from pathlib import Path\nimport subprocess\n"
                  f"p=Path({backup!r}).resolve();p.parent.mkdir(parents=True,exist_ok=True)\n"
                  f"subprocess.run(['hdc','file','recv',{device_backup!r},str(p)],check=True,capture_output=True)\n"
                  "assert p.is_file() and p.stat().st_size>0,'backup transfer failed'\n"
                  "import sqlite3\n"
                  "with sqlite3.connect(p) as db:\n"
                  " assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','invalid backup'\n")
    schema_raw = remote.hdc(["shell", f"sqlite3 {device_db} \"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';\""])
    tables = schema_raw.strip().splitlines()
    if any(not re.fullmatch(r"[A-Za-z0-9_]+", name) for name in tables):
        raise RuntimeError(f"unrecognized database schema: {tables}")
    with sqlite3.connect(fixture) as db:
        dump = "\n".join(db.iterdump())
        expected = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    script = "PRAGMA foreign_keys=OFF;\n" + "\n".join(f'DROP TABLE IF EXISTS "{name}";' for name in tables) + "\n" + dump
    with tempfile.TemporaryDirectory() as tmp:
        sql = Path(tmp) / "fixture.sql"
        sql.write_text(script)
        if sql.stat().st_size > 8 * 1024 * 1024:
            compressed = sql.with_suffix('.sql.gz')
            compressed.write_bytes(gzip.compress(sql.read_bytes()))
            digest = hashlib.sha256(sql.read_bytes()).hexdigest()
            remote.upload(compressed, host_base + '.sql.gz')
            remote.python("import gzip,hashlib,shutil\nfrom pathlib import Path\n"
                          f"source=Path({(host_base+'.sql.gz')!r});target=Path({(host_base+'.sql')!r})\n"
                          "with gzip.open(source,'rb') as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)\n"
                          f"assert hashlib.sha256(target.read_bytes()).hexdigest()=={digest!r},'SQL transfer changed'\n")
        else:
            remote.upload(sql, host_base + ".sql")
    device_sql = f"/data/local/tmp/workload-fixture-{stamp}.sql"
    remote.hdc(["file", "send", host_base + ".sql", device_sql])
    out = remote.hdc(["shell", f"sqlite3 -bail {device_db} < {device_sql}"])
    if "Error" in out or "error" in out:
        raise RuntimeError(out)
    remote.hdc(["shell", f"chown {uid}:{gid} {device_db}; chmod 660 {device_db}"])
    result = remote.hdc(["shell", f"sqlite3 {device_db} 'PRAGMA integrity_check;'"]).strip()
    if result != "ok":
        raise RuntimeError(f"fixture database integrity failed: {result}")
    return {"bundle": bundle, "database": device_db, "backup": backup,
            "fixture_tables": len(expected), "integrity_check": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--remote", default="cityuPC")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    print(json.dumps(install(Remote(args.remote), args.bundle, args.module, args.database, args.fixture), indent=2))


if __name__ == "__main__":
    main()
