"""Verify an ordinary history page and its native preference contents."""
import xml.etree.ElementTree as ET

from seed_search_history import production_states
from ui_driver import UI


def verify(layout, raw_xml, submissions, variant, bundle):
    def entries(raw):
        root = ET.fromstring(raw)
        if root.tag != 'preferences':
            raise ValueError('history preferences are not native XML')
        result = {}
        for node in root:
            key = node.attrib.get('key')
            if node.tag != 'string' or key is None or key in result:
                raise ValueError('unexpected or duplicate history preference entry')
            result[key] = node.text or ''
        return result
    if entries(raw_xml) != entries(production_states(submissions)[variant]):
        raise ValueError('history state changed or differs from the submitted history')
    texts = {n.get('text') for n in UI.nodes(layout) if n.get('bundleName') == bundle}
    expected = set(submissions if variant == 'unfixed' else list(dict.fromkeys(reversed(submissions)))[:20])
    visible = sorted(texts.intersection(expected))
    if '搜索记录' not in texts or not visible:
        raise ValueError('the normal history page does not show the prepared history')
    return {'visible_history_entries': visible, 'submitted_keywords': len(submissions),
            'retained_keywords': len(set(submissions)) if variant == 'unfixed' else min(20,len(set(submissions))),
            'native_state_preserved': True}
