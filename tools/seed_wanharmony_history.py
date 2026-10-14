#!/usr/bin/env python3
"""Prepare ordinary WebData[] in an initialized WanHarmony preference template.

No app instrumentation or auth data is added. Native installation, normal UI
verification and measured evidence remain separate required steps.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

FIELDS = {'url', 'title', 'time', 'sticky'}


def validate_entries(entries):
    if not isinstance(entries, list) or not entries:
        raise ValueError('a nonempty ordinary browsing history is required')
    urls = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != FIELDS:
            raise ValueError('history entries must contain exactly the production WebData fields')
        if (not isinstance(entry['url'], str) or len(entry['url']) > 2048
                or not isinstance(entry['title'], str) or not 1 <= len(entry['title']) <= 512
                or type(entry['sticky']) is not bool or not isinstance(entry['time'], str)):
            raise ValueError('invalid ordinary WebData field')
        url = urlsplit(entry['url'])
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError('history URL must be an ordinary HTTP(S) page without credentials')
        try:
            stamp = datetime.strptime(entry['time'], '%Y/%m/%d %H:%M:%S')
        except ValueError as exc:
            raise ValueError('history time must use the production date format') from exc
        if stamp.strftime('%Y/%m/%d %H:%M:%S') != entry['time']:
            raise ValueError('history time must use the production date format')
        if entry['url'] in urls:
            raise ValueError('production browsing history deduplicates URLs')
        urls.add(entry['url'])
    return entries


def preferences_bytes(template, entries):
    validate_entries(entries)
    root = ET.fromstring(template)
    if root.tag != 'preferences':
        raise ValueError('template must be initialized native XML preferences')
    matching = [node for node in root if node.attrib.get('key') == 'historyList']
    if len(matching) != 1 or matching[0].tag != 'string':
        raise ValueError('initialized historyList string must exist exactly once')
    existing = json.loads(matching[0].text or '')
    if not isinstance(existing, list):
        raise ValueError('initialized historyList must use a native JSON array')
    # The production constructor permits empty/default strings, and old
    # visits can contain invalid URLs. Only the replacement catalogue must
    # satisfy the stricter ordinary HTTP(S) input requirements above.
    for entry in existing:
        if (not isinstance(entry, dict) or set(entry) != FIELDS
                or any(not isinstance(entry[k], str) for k in ('url', 'title', 'time'))
                or type(entry['sticky']) is not bool):
            raise ValueError('initialized historyList does not contain production WebData objects')
    matching[0].text = json.dumps(entries, ensure_ascii=False, separators=(',', ':'))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def seed(destination, initialized, history_file):
    if destination.exists():
        raise FileExistsError('fixture destination must be fresh')
    entries = validate_entries(json.loads(history_file.read_text()))
    template = initialized.read_bytes()
    blob = preferences_bytes(template, entries)
    identity = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    receipt = {'bundle': 'org.example.wan.ohos', 'storage_key': 'historyList',
               'entries': len(entries), 'fixture_sha256': hashlib.sha256(identity).hexdigest(),
               'preferences_sha256': hashlib.sha256(blob).hexdigest(),
               'initialized_template_sha256': hashlib.sha256(template).hexdigest(),
               'catalogue_sha256': hashlib.sha256(history_file.read_bytes()).hexdigest(),
               'format': 'native PersistentStorage JSON array of production WebData objects',
               'device_validation': 'pending', 'performance_verified': False}
    destination.mkdir(parents=True)
    (destination/'persistent_storage.xml').write_bytes(blob)
    (destination/'initialized.xml').write_bytes(template)
    (destination/'history.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2)+'\n')
    (destination/'fixture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--initialized', type=Path, required=True)
    parser.add_argument('--history-json', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(seed(args.destination, args.initialized, args.history_json), indent=2))
