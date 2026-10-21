"""Recheck ordinary search requests and native result-page observations."""
import re
from urllib.parse import parse_qs,urlsplit

CASE='cloudmusic_search_result_foreach'
BUNDLE='cc.chenlvin.cloudmusic'
ARTISTS=', '.join(f'Artist {i}' for i in range(1,13))


def visible_tracks(layout,minimum=1,maximum=1000):
    texts=[]
    def visit(node,inherited=None,in_list=False):
        a=node.get('attributes',{});bundle=a.get('bundleName') or inherited;in_list=in_list or a.get('type')=='List'
        if in_list and bundle==BUNDLE and a.get('visible')!='false' and a.get('type')=='Text':texts.append(a.get('text',''))
        for child in node.get('children',[]):visit(child,bundle,in_list)
    visit(layout)
    tracks=[int(m.group(1)) for t in texts if (m:=re.fullmatch(r'Track ([1-9][0-9]*)',t))]
    if not tracks or any(not minimum<=n<=maximum for n in tracks) or ARTISTS not in texts:
        raise ValueError('native search rows differ from the ordinary catalogue')
    return sorted(set(tracks))


def search_requests(raw):
    requests=[]
    for row in raw:
        path=urlsplit(row['path'])
        if path.path!='/search':continue
        query=parse_qs(path.query)
        if query.get('type',['1'])!=['1']:continue
        requests.append({k:query.get(k) for k in ('keywords','offset','limit')})
    return requests


def verify_capture(observation):
    expected=[{'keywords':['music'],'offset':['0'],'limit':['1000']}]
    if search_requests(observation['requests'])!=expected:
        raise ValueError('expected one ordinary first-page request for 1000 songs')
    tracks=visible_tracks(observation['layout'])
    if 1 not in tracks:raise ValueError('first ordinary search result is missing')
    return tracks


def verify_functional(root,variant,signed_sha256,fixture_sha256):
    import hashlib,json
    from pathlib import Path
    from collect_music_search_pages import verify_pages
    from music_service_fixture import same_instance
    proof=json.loads((Path(root)/'validation/music-search-v2-native-pagination.json').read_text())
    if proof.get('case')!=CASE or proof.get('status')!='PASS':raise ValueError('native pagination proof missing')
    row=proof['variants'][variant]
    if row['signed_sha256']!=signed_sha256 or row['fixture_before']['sha256']!=fixture_sha256:
        raise ValueError('pagination belongs to another package or catalogue')
    same_instance(row['fixture_before'],row['fixture_after'])
    p=Path(row['observations'])
    if hashlib.sha256(p.read_bytes()).hexdigest()!=row['observations_sha256']:raise ValueError('pagination observations changed')
    raw=json.loads(p.read_text())
    if row.get('partial_observations'):
        partial=Path(row['partial_observations']);continuation=Path(row['continuation'])
        if (hashlib.sha256(partial.read_bytes()).hexdigest()!=row['partial_sha256']
                or hashlib.sha256(continuation.read_bytes()).hexdigest()!=row['continuation_sha256']):
            raise ValueError('pagination continuation provenance changed')
        first=json.loads(partial.read_text());last=json.loads(continuation.read_text())
        if (first['requests']!=raw['requests'] or set(first['layouts'])!={'first','page1_end','page2_start'}
                or any(raw['layouts'].get(k)!=v for k,v in first['layouts'].items())
                or last['page2_end']!=raw['layouts']['page2_end'] or int(last['pid'])<=0 or int(last['start_ticks'])<=0):
            raise ValueError('combined pagination does not match original native observations')
    verify_pages(raw)
