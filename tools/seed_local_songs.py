#!/usr/bin/env python3
"""Generate ordinary local-song metadata and audio outside the application."""
import argparse
import json
import math
import sqlite3
import struct
import wave
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
            # filtering, while every declared filename is a real playable asset.
            label='blue' if i%100==0 else 'jazz' if i%100==1 else 'music' if i%100==2 else 'track'
            filename=f'{label}_{i}.wav'
            path=device_directory.rstrip('/')+'/'+filename
            rows.append((i+1,f'Track {i}','Artist',path,'',''))
            files.append(filename)
        db.executemany('INSERT INTO songs (songId,name,artists,songFile,picFile,lyricFile) VALUES (?,?,?,?,?,?)',rows)
        db.execute('PRAGMA user_version=1')
    (folder/'files.json').write_text(json.dumps({'device_directory':device_directory,'files':files,'audio':'sample.wav'},indent=2)+'\n')
    return database


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--count',type=int,default=10000)
    parser.add_argument('--device-directory',default='/data/app/el2/100/base/cc.chenlvin.cloudmusic/haps/entry/files/music')
    args=parser.parse_args()
    if args.count<1:parser.error('count must be positive')
    print(generate(args.output,args.count,args.device_directory))
