"""Verify ordinary search pagination outside the performance window."""
import hashlib
import json
from pathlib import Path
from remote_device import Remote
from music_service_fixture import prepare,same_instance
from music_search_progress import CASE,visible_tracks,search_requests
ROOT=Path(__file__).resolve().parents[1]


def collect(remote, variants=('unfixed','fixed'), namespace='native-pagination-v4'):
    base=ROOT/'artifacts/candidate-builds/music-search-v2';output=base/namespace;output.mkdir(exist_ok=False)
    case=json.loads((ROOT/'cases'/CASE/'case.json').read_text())
    plan=json.loads((base/'formal-root-v3/cases'/CASE/case['testcase']['workload']).read_text())
    proof={'case':CASE,'performance_sample':False,'variants':{}}
    for v in variants:
        folder=output/v;folder.mkdir();sign=json.loads((base/CASE/v/'sign.json').read_text())
        installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
        if 'install bundle successfully' not in installed:raise ValueError(installed)
        before=prepare(remote,case);target='/home/research/ohm-clean/music-search-v2/'+namespace+'/'+v+'/observations.json'
        code=r'''import hashlib,json,subprocess,sys,re,time
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
from ui_driver import UI
subprocess.run(['hdc','rport','tcp:18490','tcp:18490'],check=True,capture_output=True)
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
def shell(c):
 p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=180);assert p.returncode==0;return p.stdout
shell('power-shell wakeup');shell('uitest uiInput swipe 630 2300 630 500 600')
plan=PAYLOAD['plan'];ui=UI(shell,plan['bundle']);ui.run([{'op':'stop'},{'op':'launch'}]);ui.run(plan['setup'])
log=Path('/home/research/ohm-clean/services/cloudmusic/requests.jsonl');offset=log.stat().st_size
path=Path(PAYLOAD['target']).resolve();path.parent.mkdir(parents=True,exist_ok=True);assert not path.exists()
observations={}
def reach(title):
 bounds=list(map(int,re.findall(r'\d+',ui.layout()['attributes']['bounds'])))
 for attempt in range(250):
  try:
   node=ui.find({'text':title,'match':'exact'},0)
   if ui.center(node)[1]<=bounds[3]*.85:return
  except RuntimeError as error:
   if not str(error).startswith('UI target not found:'):raise
  moved=shell(f'uitest uiInput swipe {int(bounds[2]*.5)} {int(bounds[3]*.78)} {int(bounds[2]*.5)} {int(bounds[3]*.3)} 4000')
  if moved.strip() not in ('','No Error'):raise ValueError('native swipe failed: '+moved)
  time.sleep(.4)
 raise ValueError('ordinary scrolling did not reach '+title)
try:
 ui.run(plan['measured']);ui.run(plan['verify']);observations['first']=ui.layout()
 reach('Track 1000');observations['page1_end']=ui.layout()
 ui.scroll_to({'text':'加载更多','match':'exact'},max_swipes=10);ui.tap({'text':'加载更多','match':'exact'})
 ui.find({'text':'Track 1001','match':'exact'},120);observations['page2_start']=ui.layout()
 reach('Track 2000');observations['page2_end']=ui.layout()
finally:
 path.write_text(json.dumps({'layouts':observations,'requests':[json.loads(x) for x in log.read_bytes()[offset:].decode().splitlines()]},ensure_ascii=False),encoding='utf8')
print('Two complete native pages reached')
'''
        print(remote.python(code,{'plan':plan,'signed_hap':sign['signed_hap'],'signed_sha256':sign['audit']['sha256'],'target':target},timeout=1800),flush=True)
        remote.download(target,folder/'observations.json');after=prepare(remote,case);same_instance(before,after)
        raw=json.loads((folder/'observations.json').read_text());verify_pages(raw)
        proof['variants'][v]={'signed_sha256':sign['audit']['sha256'],'fixture_before':before,'fixture_after':after,'observations':str(folder/'observations.json'),'observations_sha256':hashlib.sha256((folder/'observations.json').read_bytes()).hexdigest()}
        print(v,'native pagination verified',flush=True)
    proof['status']='PASS';(ROOT/'validation/music-search-v2-native-pagination.json').write_text(json.dumps(proof,indent=2)+'\n');return proof


def verify_pages(raw):
    expected=[{'keywords':['music'],'offset':[str(offset)],'limit':['1000']} for offset in (0,1000)]
    if search_requests(raw['requests'])!=expected:raise ValueError('normal pagination skipped or repeated songs')
    for name,boundary,limit in (('first',1,1000),('page1_end',1000,1000),('page2_start',1001,2000),('page2_end',2000,2000)):
        if boundary not in visible_tracks(raw['layouts'][name],maximum=limit):raise ValueError('native page boundary missing')

if __name__=='__main__':collect(Remote('hkrc'))
