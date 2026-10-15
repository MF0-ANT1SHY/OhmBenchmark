#!/usr/bin/env python3
"""Install verified business-only browsing history into a stopped application."""
import hashlib
import json
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

from seed_wanharmony_history import validate_entries, preferences_bytes

CASE = 'wanharmony_history_log_materialization'
BUNDLE = 'org.example.wan.ohos'
ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = 'history_key_only_preserving_live_preferences'


def other_preferences(blob):
    root = ET.fromstring(blob)
    def signature(node):
        return (node.tag, tuple(sorted(node.attrib.items())), node.text or '',
                tuple(signature(child) for child in node))
    return sorted((signature(node) for node in root if node.attrib.get('key') != 'historyList'), key=repr)


def fixture_state(folder):
    receipt = json.loads((folder/'fixture.json').read_text())
    entries = json.loads((folder/'history.json').read_text())
    template = (folder/'initialized.xml').read_bytes()
    blob = (folder/'persistent_storage.xml').read_bytes()
    identity = json.dumps(validate_entries(entries), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if (receipt['bundle'] != BUNDLE or receipt['storage_key'] != 'historyList'
            or receipt['entries'] != len(entries)
            or hashlib.sha256(identity).hexdigest() != receipt['fixture_sha256']
            or hashlib.sha256(template).hexdigest() != receipt['initialized_template_sha256']
            or hashlib.sha256(blob).hexdigest() != receipt['preferences_sha256']
            or blob != preferences_bytes(template, entries)):
        raise ValueError('browsing-history fixture differs from its ordinary production derivation')
    return receipt, blob


def verify_preparation(preparation, state):
    from wan_history_progress import history, PREFERENCES
    folder = Path(preparation['fixture_dir'])
    receipt, _ = fixture_state(folder)
    entries = json.loads((folder/'history.json').read_text())
    if (preparation.get('installation_verified') is not True
            or preparation['preferences'] != PREFERENCES
            or preparation['sha256'] != receipt['fixture_sha256']
            or preparation['deployed_sha256'] != verify_deployment(preparation, entries, receipt)
            or preparation['entries'] != receipt['entries']
            or history(state) != entries):
        raise ValueError('native browsing history input does not match its verified ordinary derivation')
    return receipt


def verify_deployment(preparation, entries, fixture):
    method = preparation.get('deployment')
    if method is None:
        return fixture['preferences_sha256']  # Historical exact-template preparation.
    if method != DEPLOYMENT:
        raise ValueError('unknown native history deployment method')
    directory = Path(preparation['preparation_dir'])
    before = (directory/'before.xml').read_bytes()
    deployed = (directory/'deployed.xml').read_bytes()
    expected = preferences_bytes(before, entries)
    digest = hashlib.sha256(deployed).hexdigest()
    if (hashlib.sha256(before).hexdigest() != preparation['before_sha256'] or
            digest != preparation['deployed_sha256'] or deployed != expected or
            other_preferences(before) != other_preferences(deployed)):
        raise ValueError('history-only deployment changed unrelated preferences or its recorded input')
    return digest


def install(remote, case, folder, device_path):
    if case['id'] != CASE or case['host_app']['bundle_name'] != BUNDLE:
        raise ValueError('browsing-history fixture targets a different case or application')
    if not re.fullmatch(r'/data/app/el[12]/100/base/org\.example\.wan\.ohos/'
                        r'(?:haps/entry/)?files/persistent_storage(?:\.xml)?', device_path):
        raise ValueError('use the actual initialized native persistent-storage path')
    receipt, _ = fixture_state(folder)
    entries = json.loads((folder/'history.json').read_text())
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
                  f"p=Path({backup!r});p.parent.mkdir(parents=True,exist_ok=True)\n"
                  f"subprocess.run(['hdc','file','recv',{device_path!r},str(p)],check=True,capture_output=True)\n"
                  "p.parent.chmod(0o700);p.chmod(0o600)\n"
                  "root=ET.fromstring(p.read_bytes())\n"
                  "assert root.tag=='preferences' and len([x for x in root if x.attrib.get('key')=='historyList' and x.tag=='string'])==1\n")
    # The fixture controls historyList, not unrelated live caches, cookies or
    # user settings. Preserve those from this stopped-app snapshot, and retain
    # the exact before/after bytes privately for subsequent evidence checks.
    directory = ROOT/'artifacts/fixture-preparations/wan-history'/stamp
    directory.mkdir(parents=True,mode=0o700,exist_ok=False)
    local_backup = directory/'before.xml'
    remote.download(backup, local_backup)
    local_backup.chmod(0o600)
    before = local_backup.read_bytes()
    blob = preferences_bytes(before, entries)
    if other_preferences(before) != other_preferences(blob):
        raise ValueError('history replacement changed unrelated ordinary preferences')
    deployed = directory/'deployed.xml'
    deployed.write_bytes(blob);deployed.chmod(0o600)
    source = f'/home/research/ohm-clean/fixtures/{stamp}/persistent_storage.xml'
    remote.upload(deployed, source)
    remote.python(f"from pathlib import Path\np=Path({source!r});p.parent.chmod(0o700);p.chmod(0o600)\n")
    temporary = f'/data/local/tmp/browsing-history-{stamp}.xml'
    remote.hdc(['file', 'send', source, temporary])
    # Preserve the existing inode and app-data security label. No application
    # methods, routes, counters, or diagnostic callbacks are invoked.
    remote.hdc(['shell', f'cp {temporary} {device_path} && chown {uid}:{gid} {device_path} && chmod 660 {device_path}'])
    verified = remote.python("import subprocess,hashlib\nfrom pathlib import Path\n"
                             f"p=Path({source+'.readback'!r})\n"
                             f"subprocess.run(['hdc','file','recv',{device_path!r},str(p)],check=True,capture_output=True)\n"
                             f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={hashlib.sha256(blob).hexdigest()!r}\n"
                             "print('VERIFIED')\n").strip()
    if verified != 'VERIFIED':
        raise ValueError('deployed browsing-history bytes did not verify')
    remote.hdc(['shell', 'rm -f '+temporary])
    return {'sha256': receipt['fixture_sha256'], 'deployed_sha256': hashlib.sha256(blob).hexdigest(),
            'deployment': DEPLOYMENT, 'preparation_dir': str(directory),
            'before_sha256': hashlib.sha256(before).hexdigest(),
            'preferences': device_path, 'backup': backup, 'entries': receipt['entries'],
            'fixture_dir': str(folder.resolve()),
            'method': 'ordinary WebData objects in the initialized native PersistentStorage array',
            'installation_verified': True, 'functional_read_verified': False}
