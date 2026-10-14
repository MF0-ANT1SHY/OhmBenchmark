#!/usr/bin/env python3
"""Prepare normal SongProps history in an initialized native preference file.

The supplied songs are business data, not performance annotations. Installation
and verification through the actual history page are separate required steps.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

MARKERS = {'_____set_replacer__', 'ace_engine_state_mgmt_set_replacer'}
FIELDS = {'img', 'name', 'creator', 'time'}


def encoded_songs(songs):
    if not isinstance(songs, list) or not songs:
        raise ValueError('a nonempty ordinary song catalogue is required')
    values = []
    for song in songs:
        if not isinstance(song, dict) or set(song) != FIELDS:
            raise ValueError('history entries must contain exactly the production SongProps fields')
        if any(not isinstance(song[k], str) or not song[k] or len(song[k]) > 2048
               for k in ('img', 'name', 'creator')):
            raise ValueError('invalid ordinary song text or image location')
        if type(song['time']) is not int or not 0 < song['time'] <= 86400:
            raise ValueError('song duration must be ordinary positive seconds')
        # CurrentPlaying writes JSON.stringify(SongProps); the persistent Set
        # therefore contains strings, not song objects or extra schema fields.
        values.append(json.dumps({k: song[k] for k in ('img', 'name', 'creator', 'time')},
                                 ensure_ascii=False, separators=(',', ':')))
    if len(set(values)) != len(values):
        raise ValueError('duplicate songs do not produce distinct Set history entries')
    return values


def preferences_bytes(template, songs):
    root = ET.fromstring(template)
    if root.tag != 'preferences':
        raise ValueError('template must be initialized native XML preferences')
    entries = [node for node in root if node.attrib.get('key') == 'history']
    if len(entries) != 1 or entries[0].tag != 'string':
        raise ValueError('initialized ordinary history string must exist exactly once')
    value = json.loads(entries[0].text or '')
    if (not isinstance(value, dict) or set(value) != {'setReplacer', 'values'}
            or value['setReplacer'] not in MARKERS or not isinstance(value['values'], list)
            or any(not isinstance(item, str) for item in value['values'])):
        raise ValueError('initialized history does not use the native Set<string> representation')
    value['values'] = encoded_songs(songs)
    entries[0].text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def seed(destination, initialized, songs_file):
    if destination.exists():
        raise FileExistsError('fixture destination must be fresh')
    songs = json.loads(songs_file.read_text())
    template = initialized.read_bytes()
    blob = preferences_bytes(template, songs)
    identity = json.dumps(encoded_songs(songs), ensure_ascii=False, separators=(',', ':')).encode()
    receipt = {'bundle': 'com.example.myapplication', 'storage_key': 'history',
               'songs': len(songs), 'fixture_sha256': hashlib.sha256(identity).hexdigest(),
               'preferences_sha256': hashlib.sha256(blob).hexdigest(),
               'initialized_template_sha256': hashlib.sha256(template).hexdigest(),
               'catalogue_sha256': hashlib.sha256(songs_file.read_bytes()).hexdigest(),
               'format': 'native PersistentStorage Set<string> containing JSON.stringify(SongProps)',
               'format_source': 'https://github.com/openharmony/arkui_ace_engine/blob/OpenHarmony-v5.1.0-Release/frameworks/bridge/declarative_frontend/state_mgmt/src/lib/sdk/persistent_storage.ts',
               'device_validation': 'pending', 'performance_verified': False}
    destination.mkdir(parents=True)
    (destination/'persistent_storage.xml').write_bytes(blob)
    (destination/'songs.json').write_text(json.dumps(songs, indent=2, ensure_ascii=False)+'\n')
    (destination/'initialized.xml').write_bytes(template)
    (destination/'fixture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--initialized', type=Path, required=True)
    parser.add_argument('--songs-json', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(seed(args.destination, args.initialized, args.songs_json), indent=2))
