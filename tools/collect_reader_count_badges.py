#!/usr/bin/env python3
"""Inspect every ordinary sidebar badge outside performance collection."""
import json
from pathlib import Path
import sys
from remote_device import Remote
from reader_count_fixture import snapshot
from reader_count_progress import database_identity,visible_badges
import hashlib

ROOT=Path(__file__).resolve().parents[1]
CASE='sheafreader_unread_counts_n_plus_1'


def collect(remote):
    root=ROOT/'artifacts/candidate-builds/reader-count-v1';output=root/'all-badges-v2';output.mkdir(exist_ok=False)
    expected=database_identity(ROOT/'artifacts/fixtures/reader-count-100x1000-v1/reader.db')['counts']
    proof={'case':CASE,'variants':{},'status':'PASS','performance_sample':False}
    for name in ('reader_count_progress.py','ui_driver.py'):
        remote.upload(ROOT/'tools'/name,'/home/research/ohm-clean/tools/'+name)
    for variant in ('unfixed','fixed'):
        folder=output/variant;folder.mkdir()
        sign=json.loads((root/CASE/variant/'sign.json').read_text())
        installed=remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
        if 'install bundle successfully' not in installed:raise ValueError(installed)
        before=snapshot(remote,folder/'before.db')
        if before['content']['counts']!=expected:raise ValueError('native badge inputs differ')
        base='/home/research/ohm-clean/reader-count-v1/all-badges-v2/'+variant
        code=r'''import hashlib,json,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
from ui_driver import UI
from reader_count_progress import visible_badges
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
def shell(c):
 p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=180);assert p.returncode==0;return p.stdout
ui=UI(shell,'com.sheafreader.hm');shell('power-shell wakeup');shell('uitest uiInput swipe 630 2300 630 500 600');ui.run([{'op':'stop'},{'op':'launch'}])
ui.find({'text':'Journal 1','match':'exact'},120)
ui.find({'type':'Button','bounds':'[195,326][296,427]','enabled':'true','match':'exact'},120)
observations=[];seen={};path=Path(PAYLOAD['output']).resolve();path.parent.mkdir(parents=True,exist_ok=True);assert not path.exists()
try:
 for attempt in range(30):
  layout=ui.layout();observations.append(layout);values=visible_badges(layout,PAYLOAD['expected'],fully_visible=True)
  for title,value in values.items():
   if title in seen:assert seen[title]==value
   seen[title]=value
  if seen==PAYLOAD['expected']:break
  ui.run([{'op':'swipe','selector':{'type':'Scroll','match':'exact'},'count':1}])
 else:raise ValueError('not all ordinary unread badges were reached')
finally:
 path.write_text(json.dumps({'observations':observations,'seen':seen},ensure_ascii=False),encoding='utf8')
print('all 100 badges verified')
'''
        print(remote.python(code,{'output':base+'/observations.json','expected':expected,'signed_hap':sign['signed_hap'],'signed_sha256':sign['audit']['sha256']},timeout=300),flush=True)
        remote.download(base+'/observations.json',folder/'observations.json')
        after=snapshot(remote,folder/'after.db')
        if before['content']!=after['content']:raise ValueError('sidebar inspection changed ordinary data')
        raw=json.loads((folder/'observations.json').read_text());seen={}
        for layout in raw['observations']:seen.update(visible_badges(layout,expected,fully_visible=True))
        if seen!=expected or seen!=raw['seen']:raise ValueError('saved layouts do not prove all badges')
        proof['variants'][variant]={'signed_sha256':sign['audit']['sha256'],'before':before,'after':after,
            'observations':str(folder/'observations.json'),'observations_sha256':hashlib.sha256((folder/'observations.json').read_bytes()).hexdigest(),'badges':seen}
    (ROOT/'validation/reader-count-all-native-badges.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':collect(Remote('hkrc'))
