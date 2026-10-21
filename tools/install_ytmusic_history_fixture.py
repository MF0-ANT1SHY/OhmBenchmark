#!/usr/bin/env python3
"""Install verified business-only listening history into a stopped application."""
import hashlib
import json
from pathlib import Path
import re
import time
import tempfile
import xml.etree.ElementTree as ET

from seed_ytmusic_history import encoded_songs, preferences_bytes

CASE = 'ytmusic_history_json_parse_per_row'
BUNDLE = 'com.example.myapplication'


def other_preferences(blob):
    root = ET.fromstring(blob)
    def signature(node):
        return (node.tag, tuple(sorted(node.attrib.items())), node.text or '',
                tuple(signature(child) for child in node))
    return sorted((signature(node) for node in root if node.attrib.get('key') != 'history'), key=repr)


def fixture_state(folder):
    receipt = json.loads((folder/'fixture.json').read_text())
    songs = json.loads((folder/'songs.json').read_text())
    template = (folder/'initialized.xml').read_bytes()
    blob = (folder/'persistent_storage.xml').read_bytes()
    identity = json.dumps(encoded_songs(songs), ensure_ascii=False, separators=(',', ':')).encode()
    if (receipt['bundle'] != BUNDLE or receipt['storage_key'] != 'history'
            or receipt['songs'] != len(songs)
            or hashlib.sha256(identity).hexdigest() != receipt['fixture_sha256']
            or hashlib.sha256(template).hexdigest() != receipt['initialized_template_sha256']
            or hashlib.sha256(blob).hexdigest() != receipt['preferences_sha256']
            or blob != preferences_bytes(template, songs)):
        raise ValueError('listening-history fixture differs from its ordinary production derivation')
    return receipt, blob


def install(remote, case, folder, device_path):
    if case['id'] != CASE or case['host_app']['bundle_name'] != BUNDLE:
        raise ValueError('listening-history fixture targets a different case or application')
    if not re.fullmatch(r'/data/app/el[12]/100/base/com\.example\.myapplication/'
                        r'(?:haps/entry/)?files/persistent_storage(?:\.xml)?', device_path):
        raise ValueError('use the actual initialized native persistent-storage path')
    receipt, blob = fixture_state(folder)
    remote.hdc(['shell', 'aa force-stop '+BUNDLE])
    if remote.hdc(['shell', 'pidof '+BUNDLE]).strip():
        raise ValueError('application must be stopped before replacing its preferences')
    owner = remote.hdc(['shell', 'ls -ln '+device_path]).split()
    if (len(owner) < 5 or not owner[0].startswith('-')
            or not all(part.isdigit() for part in owner[2:4])):
        raise ValueError('native preferences must already be initialized as a regular file')
    uid, gid = owner[2:4]
    if remote.hdc(['shell', f'test ! -e {device_path}.bak && echo READY']).strip() != 'READY':
        raise ValueError('native preference recovery backup exists; complete normal recovery first')
    stamp = str(time.time_ns())
    backup = f'/home/research/ohm-clean/backups/{BUNDLE}/{stamp}/persistent_storage.xml'
    remote.python("import subprocess,xml.etree.ElementTree as ET\nfrom pathlib import Path\n"
                  f"p=Path({backup!r}).resolve();p.parent.mkdir(parents=True,exist_ok=True)\n"
                  f"subprocess.run(['hdc','file','recv',{device_path!r},str(p)],check=True,capture_output=True)\n"
                  "root=ET.fromstring(p.read_bytes())\n"
                  "assert root.tag=='preferences' and len([x for x in root if x.attrib.get('key')=='history' and x.tag=='string'])==1\n")
    with tempfile.TemporaryDirectory() as temporary_backup:
        local_backup = Path(temporary_backup)/'existing.xml'
        remote.download(backup, local_backup)
        if other_preferences(local_backup.read_bytes()) != other_preferences((folder/'initialized.xml').read_bytes()):
            raise ValueError('unrelated ordinary preferences changed; refusing to overwrite them')
    source = f'/home/research/ohm-clean/fixtures/{stamp}/persistent_storage.xml'
    remote.upload(folder/'persistent_storage.xml', source)
    temporary = f'/data/local/tmp/listening-history-{stamp}.xml'
    remote.hdc(['file', 'send', source, temporary])
    # Preserve the existing inode and app-data security label. No application
    # methods, routes, counters, or diagnostic callbacks are invoked.
    remote.hdc(['shell', f'cp {temporary} {device_path} && chown {uid}:{gid} {device_path} && chmod 660 {device_path}'])
    verified = remote.python("import subprocess,hashlib\nfrom pathlib import Path\n"
                             f"p=Path({source+'.readback'!r}).resolve()\n"
                             f"subprocess.run(['hdc','file','recv',{device_path!r},str(p)],check=True,capture_output=True)\n"
                             f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={hashlib.sha256(blob).hexdigest()!r}\n"
                             "print('VERIFIED')\n").strip()
    if verified != 'VERIFIED':
        raise ValueError('deployed listening-history bytes did not verify')
    remote.hdc(['shell', 'rm -f '+temporary])
    return {'sha256': receipt['fixture_sha256'], 'deployed_sha256': receipt['preferences_sha256'],
            'preferences': device_path, 'backup': backup, 'songs': receipt['songs'],
            'fixture_dir': str(folder.resolve()),
            'method': 'ordinary SongProps strings in the initialized native PersistentStorage Set',
            'installation_verified': True, 'functional_read_verified': False}
