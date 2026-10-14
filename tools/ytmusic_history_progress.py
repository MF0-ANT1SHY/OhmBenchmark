"""Verify actual history rows and unchanged ordinary native history storage."""
import json
import re
import xml.etree.ElementTree as ET

from install_ytmusic_history_fixture import BUNDLE, CASE
from seed_ytmusic_history import MARKERS, encoded_songs
from ui_driver import UI


def verify_layout(layout, songs):
    encoded_songs(songs)
    expected = {(song['name'], song['creator']) for song in songs}
    observed = set()
    texts = {node.get('text') for node in UI.nodes(layout)
             if node.get('bundleName') == BUNDLE and node.get('visible') != 'false'}
    if '历史记录' not in texts:
        raise ValueError('the actual listening-history page is not visible')
    def walk(node, bundle=None):
        attributes = node.get('attributes', {})
        bundle = attributes.get('bundleName') or bundle
        if bundle == BUNDLE and attributes.get('type') == 'Row' and attributes.get('visible') != 'false':
            nodes=list(UI.nodes(node,bundle))
            # Do not combine a title from one row and a creator from another
            # through a surrounding layout Row.
            row = {item.get('text') for item in nodes
                   if item.get('bundleName') == BUNDLE and item.get('visible') != 'false'}
            if sum(item.get('type')=='Row' for item in nodes)==1:
                observed.update(pair for pair in expected if pair[0] in row and pair[1] in row)
        for child in node.get('children', []):
            walk(child, bundle)
    walk(layout)
    if not observed:
        raise ValueError('no ordinary song name and creator are visible in the same history row')
    return {'catalogue_songs': len(songs), 'visible_songs': [list(pair) for pair in sorted(observed)]}


def verify_state(raw, songs):
    root = ET.fromstring(raw)
    if root.tag != 'preferences':
        raise ValueError('history storage is not native preferences')
    entries = [node for node in root if node.attrib.get('key') == 'history']
    if len(entries) != 1 or entries[0].tag != 'string':
        raise ValueError('native history string missing or ambiguous')
    state = json.loads(entries[0].text or '')
    if (not isinstance(state, dict) or set(state) != {'setReplacer', 'values'}
            or state['setReplacer'] not in MARKERS or state['values'] != encoded_songs(songs)):
        raise ValueError('complete ordinary listening history differs from the prepared catalogue')
    return {'songs': len(songs), 'complete_history_preserved': True}


def read_state(remote, device_path):
    if not re.fullmatch(r'/data/app/el[12]/100/base/com\.example\.myapplication/'
                        r'(?:haps/entry/)?files/persistent_storage(?:\.xml)?', device_path):
        raise ValueError('unsupported ordinary history storage path')
    return {'raw_xml': remote.hdc(['shell', 'cat '+device_path]), 'preferences': device_path}


def verify_capture(observation, songs, start, end):
    if not 0 < start <= observation['started_monotonic'] <= observation['ended_monotonic'] <= end:
        raise ValueError('history rows were not observed inside the CPU capture window')
    result = verify_layout(observation['layout'], songs)
    if observation.get('rows') != result:
        raise ValueError('history row summary differs from the actual native UI')
    return result
