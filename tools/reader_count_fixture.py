"""Restore and archive full ordinary unread-count data outside profiling."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import uuid
from install_sqlite_fixture import install
from reader_count_progress import database_identity

ROOT=Path(__file__).resolve().parents[1]
DATABASE='/data/app/el2/100/database/com.sheafreader.hm/entry/rdb/sheaf_reader.db'


def snapshot(remote,destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('native snapshot already exists')
    token=uuid.uuid4().hex;base='/home/research/ohm-clean/reader-count-v1/snapshots/'+token
    remote.upload(ROOT/'tools/reader_count_progress.py','/home/research/ohm-clean/tools/reader_count_progress.py')
    code='''import gzip,hashlib,json,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path('/home/research/ohm-clean/tools').resolve()))
from reader_count_progress import database_identity
p=Path(PAYLOAD['base']+'.db').resolve();p.parent.mkdir(parents=True,exist_ok=True)
device='/data/local/tmp/reader-count-'+PAYLOAD['token']+'.db'
try:
 r=subprocess.run(['hdc','shell',"sqlite3 "+PAYLOAD['database']+" '.backup "+device+"'"],capture_output=True,text=True,timeout=90)
 assert r.returncode==0 and not r.stderr,r.stdout+r.stderr
 r=subprocess.run(['hdc','file','recv',device,str(p)],capture_output=True,text=True,timeout=180)
 assert r.returncode==0 and p.is_file(),r.stdout+r.stderr
 data=database_identity(p)
 with p.open('rb') as src,gzip.open(str(p)+'.gz','wb') as dst:shutil.copyfileobj(src,dst)
 print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'content':data,'remote_database':str(p)}))
finally:
 subprocess.run(['hdc','shell','rm -f '+device],capture_output=True,timeout=90)
'''
    receipt=json.loads(remote.python(code,{'base':base,'token':token,'database':DATABASE},timeout=300))
    packed=destination.with_suffix('.db.gz');remote.download(base+'.db.gz',packed)
    with gzip.open(packed,'rb') as src,destination.open('wb') as dst:shutil.copyfileobj(src,dst)
    if hashlib.sha256(destination.read_bytes()).hexdigest()!=receipt['sha256'] or database_identity(destination)!=receipt['content']:
        raise ValueError('native full-table snapshot changed in transit')
    receipt['local_database']=str(destination);destination.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def prepare(remote,fixture,output):
    fixture=Path(fixture);expected=database_identity(fixture)
    installation=install(remote,'com.sheafreader.hm','entry','sheaf_reader.db',fixture)
    actual=snapshot(remote,Path(output)/'before.db')
    if actual['content']!=expected:raise ValueError('installed native table contents differ from fixture')
    return {'installation':installation,'snapshot':actual,'content':expected,
            'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest()}
