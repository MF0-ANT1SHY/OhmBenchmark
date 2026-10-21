"""Verify the complete ordinary ten-city forecasts and live service identity."""
import hashlib,json
from pathlib import Path
from weather_hourly_data_service import CITIES,forecast,response
ROOT=Path(__file__).resolve().parents[1]

def prepare(remote):
    source=hashlib.sha256((ROOT/'tools/weather_hourly_data_service.py').read_bytes()).hexdigest()
    launcher=hashlib.sha256((ROOT/'tools/weather_hourly_workstation_lease.py').read_bytes()).hexdigest()
    expected={ '/v3/weather/weatherInfo?city='+city+'&extensions=all':hashlib.sha256(response('/v3/weather/weatherInfo?city='+city+'&extensions=all','reference')[1]).hexdigest() for city in CITIES}
    code=r'''import hashlib,json,sys,urllib.request
from pathlib import Path
base=Path('/home/research/ohm-clean/services/weather_hourly').resolve();sys.path.insert(0,str(base))
from workstation_process import identity
p=json.loads((base/'process.json').read_text());first=identity(p['pid']);assert first==p['identity'] and p['launcher'] in first['command']
for key in ('source','launcher'):assert hashlib.sha256(Path(p[key]).read_bytes()).hexdigest()==p[key+'_sha256']==PAYLOAD[key+'_sha256']
assert hashlib.sha256((base/'weather_session_data_service.py').read_bytes()).hexdigest()==p['daily_sha256']==PAYLOAD['daily_sha256']
assert p['base_url']=='http://127.0.0.1:18496' and p['catalogue_sha256']==PAYLOAD['catalogue_sha256']
for path,digest in PAYLOAD['responses'].items():
 with urllib.request.urlopen(p['base_url']+path,timeout=10) as result:data=json.loads(result.read())
 data['issuedAt']='reference';assert hashlib.sha256(json.dumps(data,ensure_ascii=False).encode()).hexdigest()==digest
assert identity(p['pid'])==first
print(json.dumps(p))
'''
    return json.loads(remote.python(code,{'daily_sha256':hashlib.sha256((ROOT/'tools/weather_session_data_service.py').read_bytes()).hexdigest(),'source_sha256':source,'launcher_sha256':launcher,'catalogue_sha256':hashlib.sha256(json.dumps({c:forecast(c,'reference') for c in CITIES},sort_keys=True).encode()).hexdigest(),'responses':expected},timeout=90))
