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
import tarfile
import io
from pathlib import Path

APP_FILES = '/data/app/el2/100/base/cc.chenlvin.cloudmusic/haps/entry/files'


def audio_archive(path, files, blob):
    """Use separate audio inodes below the device's 4096-link limit."""
    digest=hashlib.sha256(blob).hexdigest()[:16]
    parts={name:f'sample-{digest}-{i//2000}.mp3' for i,name in enumerate(files)}
    with tarfile.open(path,'w',format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(set(parts.values())):
            info=tarfile.TarInfo(name)
            # App UIDs exceed USTAR's octal field. Extract portably as root,
            # then restore the real app owner on just these audio inodes.
            info.size=len(blob);info.mode=0o660
            archive.addfile(info,io.BytesIO(blob))
        for name,part in parts.items():
            info=tarfile.TarInfo(name)
            info.type=tarfile.LNKTYPE;info.linkname=part
            info.mode=0o660
            archive.addfile(info)
    return parts


def file_inventory(listing, wanted):
    found={}
    for line in listing.splitlines():
        # ls -lni includes an inode, numeric ownership and size. A symlink must
        # never be mistaken for an absent fixture file and overwritten.
        words=line.split(' -> ',1)[0].split()
        if not words or words[-1] not in wanted:
            continue
        if len(words)<8 or not words[0].isdigit() or not words[1].startswith('-') or not words[5].isdigit():
            raise RuntimeError('unrecognized existing fixture file: '+line)
        found[words[-1]]=(int(words[0]),int(words[5]))
    return found


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
    # Native archive extraction avoids thousands of slow shell forks. Groups use
    # separate copies of the same playable audio, rather than exceeding the
    # phone filesystem's link limit. No app methods or callbacks are invoked.
    token=uuid.uuid4().hex
    host_archive=f'/home/research/ohm-clean/fixtures/cloudmusic/audio-{token}.tar'
    device_archive=f'/data/local/tmp/audio-{token}.tar'
    blob=(folder/audio_name).read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/'audio.tar'
        parts=audio_archive(archive,spec['files'],blob)
        wanted=set(spec['files'])|set(parts.values())|{audio_name}
        before=file_inventory(remote.hdc(['shell',f'ls -lni {directory}']),wanted)
        if audio_name not in before:
            raise RuntimeError('original audio is missing')
        allowed={before[audio_name][0]}
        for name in set(parts.values()) & before.keys():
            check=remote.hdc(['shell',f'sha256sum {directory}/{name}']).split()
            if not check or check[0]!=digest:
                raise RuntimeError('existing audio group differs; refusing to overwrite it')
            allowed.add(before[name][0])
        if any(name in before and before[name][0] not in allowed for name in spec['files']):
            raise RuntimeError('existing song file is not a verified fixture link; refusing to overwrite it')
        remote.upload(archive,host_archive)
    remote.hdc(['file','send',host_archive,device_archive])
    output=remote.hdc(['shell',f'tar -xf {device_archive} -C {directory} && echo AUDIO_FILES_READY'],timeout=180)
    if 'AUDIO_FILES_READY' not in output:
        raise RuntimeError('audio deployment did not finish: '+output)
    groups=' '.join(directory+'/'+name for name in sorted(set(parts.values())))
    owned=remote.hdc(['shell',f'chown {uid}:{gid} {groups} && chmod 660 {groups} && echo AUDIO_OWNER_READY'])
    if 'AUDIO_OWNER_READY' not in owned:
        raise RuntimeError('deployed audio ownership could not be restored')
    actual=remote.hdc(['shell',f'sha256sum {target}']).split()[0]
    if actual!=digest:raise RuntimeError('deployed audio checksum mismatch')
    after=file_inventory(remote.hdc(['shell',f'ls -lni {directory}']),wanted)
    for name,part in parts.items():
        if name not in after or part not in after or after[name]!=after[part] or after[name][1]!=len(blob):
            raise RuntimeError('deployed audio link is missing or incorrect: '+name)
    for part in set(parts.values()):
        check=remote.hdc(['shell',f'sha256sum {directory}/{part}']).split()
        if not check or check[0]!=digest:
            raise RuntimeError('deployed audio group checksum mismatch')
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
