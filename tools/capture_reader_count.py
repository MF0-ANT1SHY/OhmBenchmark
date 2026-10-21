import sys,json,hashlib,argparse,uuid
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tools'))
from remote_device import Remote
from reader_count_fixture import prepare,snapshot
from scheduler_cpu import compute,window_from_markers
import textwrap
ROOT=Path(__file__).resolve().parents[1]
CASE="sheafreader_unread_counts_n_plus_1"
REVISION="count-100x1000-v2"

def capture(r,v,number):
    cid=CASE;root=ROOT/"artifacts/candidate-builds/reader-count-v1";fixture=ROOT/"artifacts/fixtures/reader-count-100x1000-v1/reader.db"
    for name in ('ui_driver.py','native_trace_record.py','rss_refresh_progress.py','native_reader_count_record.py','reader_count_progress.py'):
     r.upload(ROOT/'tools'/name,'/home/research/ohm-clean/tools/'+name)
    out=root/REVISION/v/f'round-{number}';out.mkdir(parents=True,exist_ok=False)
    s=json.loads((root/cid/v/'sign.json').read_text());print(r.hdc(['install','-r',s['signed_hap']],timeout=180),flush=True)
    before=prepare(r,fixture,out);(out/'preparation.json').write_text(json.dumps(before,indent=2))
    seed=json.loads(fixture.with_suffix('.json').read_text());now=int(r.hdc(['shell','date +%s']).strip())*1000;assert 0<=now-seed['device_fetched_ms']<55*60000,'fixture no longer represents a recent refresh'
    plan={'bundle':'com.sheafreader.hm','ability':'EntryAbility','description':'Open the reader and load subscription unread badges','setup':[{'op':'stop'}],'measured':[{'op':'launch'}],'verify':[{'op':'wait','selector':{'text':'Journal 1 article 1','match':'exact'},'timeout_s':120},{'op':'wait','selector':{'type':'Button','bounds':'[195,326][296,427]','enabled':'true','match':'exact'},'timeout_s':120}]}
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    remote='/home/research/ohm-clean/reader-count-v1/'+REVISION+'/'+v+f'/round-{number}-'+uuid.uuid4().hex
    code=r'''
import sys,subprocess,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
assert hashlib.sha256(Path(PAYLOAD['signed_hap']).read_bytes()).hexdigest()==PAYLOAD['signed_sha256']
from native_reader_count_record import record
from ui_driver import UI
def shell(c):
    p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=180)
    assert p.returncode==0,p.stdout+p.stderr
    return p.stdout
result=record(UI(shell,'com.sheafreader.hm'),PAYLOAD['plan'],Path(PAYLOAD['root']),PAYLOAD['expected'])
print(json.dumps({'status':result['status'],'error':result.get('error')}))
'''
    print(r.python(textwrap.dedent(code),{'root':remote,'plan':plan,'expected':before['content']['counts'],'signed_hap':s['signed_hap'],'signed_sha256':s['audit']['sha256']},timeout=600),flush=True)
    r.download(remote+'/capture.json',out/'capture.json');c=json.loads((out/'capture.json').read_text());assert c['status']=='CAPTURED',c.get('error')
    after=snapshot(r,out/'after.db');assert after['content']==before['content'],'full ordinary data changed'
    r.download(remote+'/trace.htrace',out/'trace.htrace')
    a,b=window_from_markers(out/'trace.htrace',c['marker_token'],c['pids']);c['scheduler_cpu']=compute(out/'trace.htrace',c['pids'],a,b,c['online_cpus_before']);c['signed_sha256']=s['audit']['sha256'];c['reader_fixture_before']=before;c['reader_fixture_after']=after
    c.update(case=cid,variant=v,round=number,measurement_revision=REVISION,fixture_sha256=before['fixture_sha256'],plan_sha256=hashlib.sha256((out/'plan.json').read_bytes()).hexdigest(),device_clock_before_ms=now,device_clock_after_ms=int(r.hdc(['shell','date +%s']).strip())*1000,seed_fetched_ms=seed['device_fetched_ms'],remote_artifacts=remote)
    (out/'capture.json').write_text(json.dumps(c,indent=2)+'\n');print(v,c['scheduler_cpu']['app_cpu_ms'],flush=True)
    return c

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("variant",choices=("unfixed","fixed"));p.add_argument("--round",type=int,required=True,choices=(1,2,3));a=p.parse_args();capture(Remote("hkrc"),a.variant,a.round)
