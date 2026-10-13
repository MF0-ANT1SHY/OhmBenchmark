#!/usr/bin/env python3
"""Generate ordinary local-song metadata and audio outside the application."""
import argparse
import json
import math
import sqlite3
import struct
import wave
import re
import hashlib
from pathlib import Path


def generate(folder, count, device_directory):
    folder.mkdir(parents=True,exist_ok=True)
    database=folder/'LocalSongs.db'
    if database.exists():
        raise FileExistsError(database)
    with wave.open(str(folder/'sample.wav'),'wb') as audio:
        audio.setparams((1,2,8000,0,'NONE','not compressed'))
        audio.writeframes(b''.join(struct.pack('<h',round(1200*math.sin(2*math.pi*220*i/8000))) for i in range(8000*60)))
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE songs (id INTEGER PRIMARY KEY AUTOINCREMENT,songId INTEGER,name TEXT NOT NULL,artists TEXT NOT NULL,songFile TEXT NOT NULL,picFile TEXT,lyricFile TEXT)')
        rows=[]
        files=[]
        for i in range(count):
            # Rare search matches exercise full-table materialization versus native
            # filtering. Deployment makes every filename a playable hard link.
            label='blue' if i%100==0 else 'jazz' if i%100==1 else 'music' if i%100==2 else 'track'
            filename=f'{label}_{i}.wav'
            path=device_directory.rstrip('/')+'/'+filename
            rows.append((i+1,f'Track {i}','Artist',path,'',''))
            files.append(filename)
        db.executemany('INSERT INTO songs (songId,name,artists,songFile,picFile,lyricFile) VALUES (?,?,?,?,?,?)',rows)
        db.execute('PRAGMA user_version=1')
    (folder/'files.json').write_text(json.dumps({'device_directory':device_directory,'files':files,'audio':'sample.wav'},indent=2)+'\n')
    return database


def deploy(folder, remote_name):
    from remote_device import Remote
    from install_sqlite_fixture import install
    spec=json.loads((folder/'files.json').read_text())
    directory=spec['device_directory']
    if not re.fullmatch(r'/data/app/el2/100/base/cc\.chenlvin\.cloudmusic/haps/entry/files/[A-Za-z0-9_-]+',directory):
        raise ValueError('invalid app audio directory')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+\.wav',name) for name in spec['files']):
        raise ValueError('invalid audio filename')
    remote=Remote(remote_name)
    receipt=install(remote,'cc.chenlvin.cloudmusic','entry','LocalSongs.db',folder/'LocalSongs.db')
    owner=remote.hdc(['shell','ls -ln '+receipt['database']]).split()
    uid,gid=owner[2:4]
    if not uid.isdigit() or not gid.isdigit():raise RuntimeError('invalid app ownership')
    audio_host='/home/research/ohm-clean/fixtures/cloudmusic/sample.wav'
    remote.upload(folder/'sample.wav',audio_host)
    remote.hdc(['shell',f'mkdir -p {directory}; chown {uid}:{gid} {directory}; chmod 770 {directory}'])
    target=directory+'/sample.wav'
    existing=remote.hdc(['shell',f'test -f {target} && sha256sum {target}']).strip()
    digest=hashlib.sha256((folder/'sample.wav').read_bytes()).hexdigest()
    if existing and existing.split()[0]!=digest:
        raise RuntimeError('existing audio differs; refusing to overwrite it')
    if not existing:
        remote.hdc(['file','send',audio_host,target])
    remote.hdc(['shell',f'chown {uid}:{gid} {target}; chmod 660 {target}'])
    # One remote shell call creates all ordinary files; no app methods or fake
    # player callbacks are invoked. Hard links avoid duplicating gigabytes of audio.
    lines=['set -e']
    for name in spec['files']:
        path=directory+'/'+name
        lines.append(f'if test -e {path}; then test {path} -ef {target}; else ln {target} {path}; fi')
    remote.python('import subprocess\n' + f"p=subprocess.run(['hdc','shell','sh'],input={chr(10).join(lines)!r},text=True,capture_output=True,timeout=120)\n"+
                  "assert p.returncode==0,p.stdout+p.stderr\n")
    receipt.update({'audio_sha256':digest,'audio_files':len(spec['files']),'fixture_sha256':hashlib.sha256((folder/'LocalSongs.db').read_bytes()).hexdigest()})
    (folder/'install.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--count',type=int,default=10000)
    parser.add_argument('--device-directory',default='/data/app/el2/100/base/cc.chenlvin.cloudmusic/haps/entry/files/music')
    parser.add_argument('--deploy-remote',help='install an already generated fixture on this SSH device workstation')
    args=parser.parse_args()
    if args.count<1:parser.error('count must be positive')
    if args.deploy_remote:
        print(json.dumps(deploy(args.output,args.deploy_remote),indent=2))
    else:
        print(generate(args.output,args.count,args.device_directory))
