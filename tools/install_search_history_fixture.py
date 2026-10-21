#!/usr/bin/env python3
"""Replace an initialized ordinary history preference file in a stopped app."""
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from seed_search_history import production_states


def fixture_state(folder,variant):
    if variant not in ('unfixed','fixed'):
        raise ValueError('invalid variant')
    receipt=json.loads((folder/'fixture.json').read_text())
    events=(folder/'submissions.json').read_bytes()
    if hashlib.sha256(events).hexdigest()!=receipt['fixture_sha256']:
        raise ValueError('search-history event identity mismatch')
    states=production_states(json.loads(events))
    blob=(folder/f'{variant}.xml').read_bytes()
    if blob!=states[variant] or hashlib.sha256(blob).hexdigest()!=receipt['variants'][variant]['sha256']:
        raise ValueError('preference file differs from ordinary production state')
    return receipt,blob


def install(remote,case,variant,folder,device_path):
    if case['id']!='interviewapp_search_history_unbounded':
        raise ValueError('history fixture is specific to the unbounded-history pair')
    bundle=case['host_app']['bundle_name']
    if bundle!='com.itcast.pass_interview':
        raise ValueError('fixture targets a different app')
    pattern=r'/data/app/el[12]/100/(?:base|database)/com\.itcast\.pass_interview/(?:[A-Za-z0-9_-]+/)*preferences/historyStore(?:\.xml)?'
    if not re.fullmatch(pattern,device_path):
        raise ValueError('use the actual initialized app history preference path')
    receipt,blob=fixture_state(folder,variant)
    remote.hdc(['shell','aa force-stop '+bundle])
    if remote.hdc(['shell','pidof '+bundle]).strip():
        raise ValueError('app must be stopped before replacing preferences')
    fields=remote.hdc(['shell','ls -ln '+device_path]).split()
    if len(fields)<5 or not fields[0].startswith('-') or not all(x.isdigit() for x in fields[2:4]):
        raise ValueError('history preferences must already be initialized as a regular file')
    uid,gid=fields[2:4]
    # Native XML reads recover .bak before reading the main file. Do not install
    # into a interrupted-write state or silently discard its recovery copy.
    ready=remote.hdc(['shell',f'test ! -e {device_path}.bak && echo READY']).strip()
    if ready!='READY':
        raise ValueError('native preference recovery backup exists; finish normal recovery first')
    stamp=str(time.time_ns())
    backup=f'/home/research/ohm-clean/backups/{bundle}/{stamp}/historyStore.xml'
    remote.python("import subprocess,xml.etree.ElementTree as ET\nfrom pathlib import Path\n"
                  f"p=Path({backup!r}).resolve();p.parent.mkdir(parents=True,exist_ok=True)\n"
                  f"subprocess.run(['hdc','file','recv',{device_path!r},str(p)],check=True,capture_output=True)\n"
                  "assert p.is_file() and ET.fromstring(p.read_bytes()).tag=='preferences','existing data is not ordinary XML preferences'\n")
    host_fixture=f'/home/research/ohm-clean/fixtures/{stamp}/historyStore.xml'
    remote.upload(folder/f'{variant}.xml',host_fixture)
    # Write the existing inode so its app-data security label is retained.
    temporary=f'/data/local/tmp/workload-preferences-{stamp}.xml'
    remote.hdc(['file','send',host_fixture,temporary])
    remote.hdc(['shell',f'cp {temporary} {device_path} && chown {uid}:{gid} {device_path} && chmod 660 {device_path}'])
    verified=remote.python("import subprocess,hashlib\nfrom pathlib import Path\n"
                           f"p=Path({host_fixture+'.readback'!r}).resolve()\n"
                           f"subprocess.run(['hdc','file','recv',{device_path!r},str(p)],check=True,capture_output=True)\n"
                           f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={hashlib.sha256(blob).hexdigest()!r}\n"
                           "print('VERIFIED')\n").strip()
    if verified!='VERIFIED':
        raise ValueError('deployed preference bytes did not verify')
    remote.hdc(['shell','rm -f '+temporary])
    return {'sha256':receipt['fixture_sha256'],'deployed_sha256':hashlib.sha256(blob).hexdigest(),
            'fixture_dir':str(folder.resolve()),
            'variant':variant,'preferences':device_path,'backup':backup,
            'method':'ordinary production preferences after identical search submissions',
            'installation_verified':True,'functional_read_verified':False}
