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
import tempfile
import uuid
import subprocess
from pathlib import Path

APP_FILES = '/data/app/el2/100/base/cc.chenlvin.cloudmusic/haps/entry/files'


def fixture_digest(folder):
    spec=json.loads((folder/'files.json').read_text())
    audio=spec['audio']
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.(mp3|wav)',audio):
        raise ValueError('invalid audio filename')
    manifest={name:hashlib.sha256((folder/name).read_bytes()).hexdigest()
              for name in ('LocalSongs.db','files.json',audio)}
    return hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()


def generate(folder, count, device_directory):
    if not re.fullmatch(re.escape(APP_FILES)+r'(?:/[A-Za-z0-9_-]+)?',device_directory):
        raise ValueError('invalid app audio directory')
    prefix=str(Path(device_directory).relative_to(APP_FILES))
    prefix='' if prefix=='.' else prefix+'/'
    folder.mkdir(parents=True,exist_ok=True)
    database=folder/'LocalSongs.db'
    if database.exists():
        raise FileExistsError(database)
    with wave.open(str(folder/'sample.wav'),'wb') as audio:
        audio.setparams((1,2,8000,0,'NONE','not compressed'))
        audio.writeframes(b''.join(struct.pack('<h',round(1200*math.sin(2*math.pi*220*i/8000))) for i in range(8000*60)))
    subprocess.run(['ffmpeg','-v','error','-i',str(folder/'sample.wav'),'-map_metadata','-1',
                    '-codec:a','libmp3lame','-b:a','32k',str(folder/'sample.mp3')],check=True)
    (folder/'sample.wav').unlink()
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE songs (id INTEGER PRIMARY KEY AUTOINCREMENT,songId INTEGER,name TEXT NOT NULL,artists TEXT NOT NULL,songFile TEXT NOT NULL,picFile TEXT,lyricFile TEXT)')
        rows=[]
        files=[]
        for i in range(count):
            # Rare search matches exercise full-table materialization versus native
            # filtering. Deployment makes every filename a playable hard link.
            label='blue' if i%100==0 else 'jazz' if i%100==1 else 'music' if i%100==2 else 'track'
            filename=f'{label}_{i}.mp3'
            # Business code prepends filesDir when reading songFile. Importing a
            # local file uses songId=0 and a relative filename, not an absolute path.
            rows.append((0,f'Track {i}','Artist',prefix+filename,'',''))
            files.append(filename)
        db.executemany('INSERT INTO songs (songId,name,artists,songFile,picFile,lyricFile) VALUES (?,?,?,?,?,?)',rows)
        db.execute('PRAGMA user_version=1')
    (folder/'files.json').write_text(json.dumps({'device_directory':device_directory,'files':files,'audio':'sample.mp3'},indent=2)+'\n')
    return database


def deploy(folder, remote_name):
    from remote_device import Remote
    from install_sqlite_fixture import install
    spec=json.loads((folder/'files.json').read_text())
    directory=spec['device_directory']
    if not re.fullmatch(re.escape(APP_FILES)+r'(?:/[A-Za-z0-9_-]+)?',directory):
        raise ValueError('invalid app audio directory')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+\.(mp3|wav)',name) for name in spec['files']):
        raise ValueError('invalid audio filename')
    digest_fixture=fixture_digest(folder)
    prefix=str(Path(directory).relative_to(APP_FILES))
    prefix='' if prefix=='.' else prefix+'/'
    with sqlite3.connect(f'file:{(folder/"LocalSongs.db").resolve()}?mode=ro',uri=True) as db:
        actual_files={r[0] for r in db.execute('SELECT songFile FROM songs')}
    if actual_files!={prefix+name for name in spec['files']}:
        raise ValueError('database audio paths do not match deployed relative filenames')
    remote=Remote(remote_name)
    receipt=install(remote,'cc.chenlvin.cloudmusic','entry','LocalSongs.db',folder/'LocalSongs.db')
    owner=remote.hdc(['shell','ls -ln '+receipt['database']]).split()
    uid,gid=owner[2:4]
    if not uid.isdigit() or not gid.isdigit():raise RuntimeError('invalid app ownership')
    audio_name=spec['audio']
    audio_host='/home/research/ohm-clean/fixtures/cloudmusic/'+audio_name
    remote.upload(folder/audio_name,audio_host)
    remote.hdc(['shell',f'mkdir -p {directory}; chown {uid}:{gid} {directory}; chmod 770 {directory}'])
    target=directory+'/'+audio_name
    existing=remote.hdc(['shell',f'test -f {target} && sha256sum {target}']).strip()
    digest=hashlib.sha256((folder/audio_name).read_bytes()).hexdigest()
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
    lines.append('echo AUDIO_FILES_READY')
    token=uuid.uuid4().hex
    host_script=f'/home/research/ohm-clean/fixtures/cloudmusic/files-{token}.sh'
    device_script=f'/data/local/tmp/files-{token}.sh'
    with tempfile.TemporaryDirectory() as tmp:
        script=Path(tmp)/'files.sh';script.write_text('\n'.join(lines)+'\n')
        remote.upload(script,host_script)
    remote.hdc(['file','send',host_script,device_script])
    output=remote.hdc(['shell',f'sh {device_script}'],timeout=180)
    if 'AUDIO_FILES_READY' not in output:
        raise RuntimeError('audio deployment did not finish: '+output)
    actual=remote.hdc(['shell',f'sha256sum {target}']).split()[0]
    if actual!=digest:raise RuntimeError('deployed audio checksum mismatch')
    receipt.update({'audio_sha256':digest,'audio_files':len(spec['files']),
                    'database_sha256':hashlib.sha256((folder/'LocalSongs.db').read_bytes()).hexdigest(),
                    'fixture_sha256':digest_fixture})
    (folder/'install.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--count',type=int,default=10000)
    parser.add_argument('--device-directory',default=APP_FILES)
    parser.add_argument('--deploy-remote',help='install an already generated fixture on this SSH device workstation')
    args=parser.parse_args()
    if args.count<1:parser.error('count must be positive')
    if args.deploy_remote:
        print(json.dumps(deploy(args.output,args.deploy_remote),indent=2))
    else:
        print(generate(args.output,args.count,args.device_directory))
