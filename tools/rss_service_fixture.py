"""Verify ordinary RSS payloads and service identity outside the app."""
import hashlib
import json
from pathlib import Path

from rss_data_service import Catalogue


def prepare(remote, case):
    if (case['host_app']['bundle_name'] != 'com.sheafreader.hm'
            or not case['id'].startswith('sheafreader_')):
        raise ValueError('RSS fixture provided to a different app')
    source = Path(__file__).with_name('rss_data_service.py')
    catalogue = Catalogue('http://127.0.0.1:18491')
    files = {f'/feeds/{i}.xml': hashlib.sha256(catalogue.feed(i)).hexdigest()
             for i in range(1, 11)}
    files['/subscriptions.opml'] = hashlib.sha256(catalogue.opml()).hexdigest()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    code = """import hashlib,json,urllib.request
from pathlib import Path
base=Path('/home/research/ohm-clean/services/rss')
process=json.loads((base/'process.json').read_text())
pid=process['pid'];proc=Path('/proc')/str(pid)
before=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
assert process['base_url']=='http://127.0.0.1:18491'
assert process['feeds']==10 and process['articles_per_feed']==100
assert process['source'].encode() in (proc/'cmdline').read_bytes()
assert hashlib.sha256(Path(process['source']).read_bytes()).hexdigest()==PAYLOAD['source_sha256']
files={}
for path,expected in PAYLOAD['files'].items():
 with urllib.request.urlopen(process['base_url']+path,timeout=30) as response:
  assert response.status==200
  files[path]=hashlib.sha256(response.read()).hexdigest()
 assert files[path]==expected,'ordinary RSS payload changed: '+path
assert (proc/'stat').read_text().rsplit(')',1)[1].split()[19]==before
digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert digest==PAYLOAD['sha256']
print(json.dumps({'sha256':digest,'source_sha256':PAYLOAD['source_sha256'],
 'base_url':process['base_url'],'service_pid':pid,'service_start_ticks':int(before),
 'files':files,'feeds':10,'articles_per_feed':100,
 'method':'ordinary RSS/OPML responses fetched and hashed outside profiling',
 'functional_read_verified':False}))
"""
    return json.loads(remote.python(code, {
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'files': files, 'sha256': digest,
    }, timeout=300))


def same_instance(before, after):
    keys = ('sha256', 'source_sha256', 'base_url', 'service_pid', 'service_start_ticks')
    if any(before.get(k) is None or before.get(k) != after.get(k) for k in keys):
        raise ValueError('RSS data service changed during the workload')
