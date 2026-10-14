#!/usr/bin/env python3
"""Prepare real API article cache states without changing application code.

The same native file supplies the old full homeList and the first-page
homeListCache. The clean business variants select their existing storage keys.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

KEYS = {'homeList', 'homeListCache'}


def catalogue(pages):
    articles, seen, sources = [], set(), []
    for path in pages:
        blob = path.read_bytes(); response = json.loads(blob)
        if response.get('errorCode') != 0 or not isinstance(response.get('data', {}).get('datas'), list):
            raise ValueError('successful ordinary home article API pages required')
        sources.append({'file': str(path), 'sha256': hashlib.sha256(blob).hexdigest()})
        for article in response['data']['datas']:
            if (not isinstance(article, dict) or type(article.get('id')) is not int or article['id'] <= 0
                    or any(not isinstance(article.get(k), str) for k in ('title', 'desc', 'chapterName', 'link'))):
                raise ValueError('invalid ordinary API article')
            if article['id'] not in seen:
                seen.add(article['id']); articles.append(article)
    if len(articles) <= 20:
        raise ValueError('an accumulated list larger than one ordinary page is required')
    return articles, sources


def preferences_bytes(template, articles):
    root = ET.fromstring(template)
    if root.tag != 'preferences':
        raise ValueError('initialized native preferences required')
    for key, values in [('homeList', articles), ('homeListCache', articles[:20])]:
        matching = [n for n in root if n.attrib.get('key') == key]
        if len(matching) != 1 or matching[0].tag != 'string' or not isinstance(json.loads(matching[0].text or ''), list):
            raise ValueError('both actual initialized native cache arrays are required')
        matching[0].text = json.dumps(values, ensure_ascii=False, separators=(',', ':'))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def seed(destination, initialized, pages):
    if destination.exists():
        raise FileExistsError('fixture destination must be fresh')
    articles, sources = catalogue(pages)
    template = initialized.read_bytes(); blob = preferences_bytes(template, articles)
    identity = json.dumps(articles, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    receipt = {'case': 'wanharmony_persisted_home_list_growth', 'bundle': 'org.example.wan.ohos',
               'articles': len(articles), 'first_page_articles': 20, 'sources': sources,
               'fixture_sha256': hashlib.sha256(identity).hexdigest(),
               'preferences_sha256': hashlib.sha256(blob).hexdigest(),
               'initialized_template_sha256': hashlib.sha256(template).hexdigest(),
               'same_native_bytes_for_both_variants': True, 'app_source_modified': False,
               'payload_padding': False, 'network_load_more_verified': False,
               'cold_cache_ui_verified': False, 'performance_accepted': False}
    destination.mkdir(parents=True)
    (destination/'articles.json').write_text(json.dumps(articles, ensure_ascii=False, indent=2)+'\n')
    (destination/'persistent_storage.xml').write_bytes(blob)
    (destination/'initialized.xml').write_bytes(template)
    (destination/'fixture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination', type=Path)
    p.add_argument('--initialized', type=Path, required=True)
    p.add_argument('--api-pages', type=Path, nargs='+', required=True)
    args = p.parse_args()
    print(json.dumps(seed(args.destination, args.initialized, args.api_pages), indent=2))
