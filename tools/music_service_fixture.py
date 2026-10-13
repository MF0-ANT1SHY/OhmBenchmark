"""Pin ordinary externally hosted music data, without adding app endpoints."""
import hashlib
import json
from pathlib import Path

from cloudmusic_data_service import Catalogue


def prepare(remote,case):
    if case['host_app']['bundle_name']!='cc.chenlvin.cloudmusic':
        raise ValueError('music service provided to a different app')
    if case['id'] not in {'cloudmusic_songcard_artists_concat','cloudmusic_search_result_foreach','cloudmusic_indexof_in_render'}:
        raise ValueError('online catalogue is not input preparation for this workload')
    source=Path(__file__).with_name('cloudmusic_data_service.py')
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    catalogue=Catalogue(10000,'http://127.0.0.1:18490',12)
    encoded=json.dumps({'songs':catalogue.songs,'playlist':catalogue.playlist},
                       sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    expected=hashlib.sha256(encoded).hexdigest()
    code="""import hashlib,json,urllib.request
from pathlib import Path
base=Path('/home/research/ohm-clean/services/cloudmusic')
process=json.loads((base/'process.json').read_text())
pid=process['pid'];proc=Path('/proc')/str(pid)
before=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
assert process['base_url']=='http://127.0.0.1:18490'
assert process['count']==10000
assert process['source'].encode() in (proc/'cmdline').read_bytes(),'owned service process not live'
assert hashlib.sha256(Path(process['source']).read_bytes()).hexdigest()==PAYLOAD['source_sha256']
def get(path):
 with urllib.request.urlopen(process['base_url']+path,timeout=30) as r:return json.load(r)
songs=[]
for offset in range(0,10000,1000):
 response=get('/playlist/track/all?id=1&offset='+str(offset)+'&limit=1000')
 assert response['code']==200 and len(response['songs'])==1000
 songs.extend(response['songs'])
playlist=get('/playlist/detail?id=1')['playlist']
digest=hashlib.sha256(json.dumps({'songs':songs,'playlist':playlist},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
assert digest==PAYLOAD['fixture_sha256'],'ordinary music data changed'
assert (proc/'stat').read_text().rsplit(')',1)[1].split()[19]==before,'service restarted during fixture check'
print(json.dumps({'sha256':digest,'source_sha256':PAYLOAD['source_sha256'],'songs':len(songs),
 'artist_count':12,'base_url':process['base_url'],'service_pid':pid,'service_start_ticks':int(before),
 'method':'ordinary API catalogue fetched and hashed before profiling; no app instrumentation'}))
"""
    return json.loads(remote.python(code,{'source_sha256':source_hash,'fixture_sha256':expected},timeout=300))


def same_instance(before,after):
    keys=('sha256','source_sha256','base_url','service_pid','service_start_ticks')
    if any(before.get(k)!=after.get(k) or before.get(k) is None for k in keys):
        raise ValueError('music data service changed during the workload')
