"""Verify ordinary forecasts and remote icons against the bundled icon bytes."""
import hashlib
import json
from pathlib import Path
import zipfile
from weather_data_service import CITIES,forecast

ROOT=Path(__file__).resolve().parents[1]


def prepare(remote,fixed_hap):
    with zipfile.ZipFile(fixed_hap) as package:
        icons={name:hashlib.sha256(package.read('resources/rawfile/weather/'+name)).hexdigest()
               for name in ('sunny.img','overcast.img','cloudy.img','rain.img')}
    source_hash=hashlib.sha256((ROOT/'tools/weather_data_service.py').read_bytes()).hexdigest()
    catalogue_hash=hashlib.sha256(json.dumps({code:forecast(code) for code in CITIES},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    code=r'''import hashlib,json,sys,urllib.request
from pathlib import Path
base=Path('/home/research/ohm-clean/services/weather').resolve();sys.path.insert(0,str(base))
from workstation_process import identity
p=json.loads((base/'process.json').read_text());first=identity(p['pid'])
assert first==p['identity'] and p['launcher'] in first['command']
assert hashlib.sha256(Path(p['source']).read_bytes()).hexdigest()==PAYLOAD['source_sha256']==p['source_sha256']
assert hashlib.sha256(Path(p['launcher']).read_bytes()).hexdigest()==p['launcher_sha256']
assert p['icon_delay_s']==4.0 and p['base_url']=='http://127.0.0.1:18492'
def get(path):
 with urllib.request.urlopen(p['base_url']+path,timeout=15) as response:return response.read()
icons={name:hashlib.sha256(get('/weather/'+name)).hexdigest() for name in PAYLOAD['icons_sha256']}
assert icons==PAYLOAD['icons_sha256']==p['icons_sha256']
forecasts={city:json.loads(get('/v3/weather/weatherInfo?city='+city+'&extensions=all')) for city in PAYLOAD['cities']}
digest=hashlib.sha256(json.dumps(forecasts,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
assert digest==PAYLOAD['forecasts_sha256']==p['forecasts_sha256']
assert identity(p['pid'])==first
print(json.dumps({'source_sha256':p['source_sha256'],'launcher_sha256':p['launcher_sha256'],'icons_sha256':icons,'forecasts_sha256':digest,'service_pid':p['pid'],'service_identity':first,'icon_delay_s':p['icon_delay_s'],'base_url':p['base_url'],'method':'All ordinary forecast and image responses checked outside profiling; exact image identity with fixed signed HAP.'}))
'''
    return json.loads(remote.python(code,{'source_sha256':source_hash,'icons_sha256':icons,'cities':list(CITIES),'forecasts_sha256':catalogue_hash},timeout=90))


def same_instance(before,after):
    if before!=after:raise ValueError('ordinary weather source or process changed')
