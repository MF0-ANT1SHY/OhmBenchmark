"""Verify the complete ordinary song catalogue and live service identity."""
import hashlib,json
from pathlib import Path
from ytsearch_data_service import CATALOGUE,response
ROOT=Path(__file__).resolve().parents[1]

def prepare(remote):
    source=hashlib.sha256((ROOT/'tools/ytsearch_data_service.py').read_bytes()).hexdigest()
    launcher=hashlib.sha256((ROOT/'tools/ytsearch_workstation_lease.py').read_bytes()).hexdigest()
    expected={ '/search?keyword='+ 'electronic'[:n]:hashlib.sha256(response('/search?keyword='+'electronic'[:n])[2]).hexdigest() for n in range(1,11)}
    expected['/cover.svg']=hashlib.sha256(response('/cover.svg')[2]).hexdigest()
    code=r'''import hashlib,json,sys,urllib.request
from pathlib import Path
base=Path('/home/research/ohm-clean/services/ytsearch').resolve();sys.path.insert(0,str(base))
from workstation_process import identity
p=json.loads((base/'process.json').read_text());first=identity(p['pid']);assert first==p['identity'] and p['launcher'] in first['command']
for key in ('source','launcher'):assert hashlib.sha256(Path(p[key]).read_bytes()).hexdigest()==p[key+'_sha256']==PAYLOAD[key+'_sha256']
assert p['base_url']=='http://127.0.0.1:18493' and p['catalogue_sha256']==PAYLOAD['catalogue_sha256']
for path,digest in PAYLOAD['responses'].items():
 with urllib.request.urlopen(p['base_url']+path,timeout=10) as result:assert hashlib.sha256(result.read()).hexdigest()==digest
assert identity(p['pid'])==first
print(json.dumps(p))
'''
    return json.loads(remote.python(code,{'source_sha256':source,'launcher_sha256':launcher,'catalogue_sha256':hashlib.sha256(json.dumps(CATALOGUE,sort_keys=True).encode()).hexdigest(),'responses':expected},timeout=90))
