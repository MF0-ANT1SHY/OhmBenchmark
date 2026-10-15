"""Prepare only the dedicated native search-history store of the stopped app."""
import hashlib
from pathlib import Path
import time

from interview_history_progress import BUNDLE,PREFERENCES,empty_preferences,keywords

CASE='interviewapp_search_history_sync_flush'
ROOT=Path(__file__).resolve().parents[1]
IDENTITY=hashlib.sha256(b'normal native historyStore with zero keywords').hexdigest()


def verify(preparation):
    directory=Path(preparation['preparation_dir']);before=(directory/'before.xml').read_bytes();deployed=(directory/'deployed.xml').read_bytes()
    if (preparation.get('installation_verified') is not True or preparation['case']!=CASE or
            preparation['variant'] not in ('unfixed','fixed') or preparation['preferences']!=PREFERENCES or
            preparation['sha256']!=IDENTITY or hashlib.sha256(before).hexdigest()!=preparation['before_sha256'] or
            deployed!=empty_preferences(before) or keywords(deployed) or
            hashlib.sha256(deployed).hexdigest()!=preparation['deployed_sha256']):
        raise ValueError('fresh empty native history preparation is not proven')
    return IDENTITY


def prepare(remote,case,variant):
    if case['id']!=CASE or case['host_app']['bundle_name']!=BUNDLE or variant not in ('unfixed','fixed'):
        raise ValueError('empty history preparation targets a different case or app')
    remote.hdc(['shell','aa force-stop '+BUNDLE])
    if remote.hdc(['shell','pidof '+BUNDLE]).strip():raise ValueError('app must be stopped before preparation')
    if remote.hdc(['shell','test ! -e '+PREFERENCES+'.bak && echo READY']).strip()!='READY':
        raise ValueError('finish normal preference recovery before preparation')
    fields=remote.hdc(['shell','ls -ln '+PREFERENCES]).split()
    if len(fields)<5 or not fields[0].startswith('-') or not all(v.isdigit() for v in fields[2:4]):
        raise ValueError('initialized regular native history preferences required')
    uid,gid=fields[2:4];stamp=str(time.time_ns());target='/home/research/ohm-clean/fixture-preparations/interview-empty-'+stamp
    remote.python("import subprocess\nfrom pathlib import Path\np=Path(PAYLOAD['root']);p.mkdir(parents=True,exist_ok=False,mode=0o700)\nsubprocess.run(['hdc','file','recv',PAYLOAD['preferences'],str(p/'before.xml')],check=True,capture_output=True,timeout=30)\n(p/'before.xml').chmod(0o600)",{'root':target,'preferences':PREFERENCES})
    local=ROOT/'artifacts/fixture-preparations/interview-empty'/stamp;local.mkdir(parents=True,mode=0o700)
    remote.download(target+'/before.xml',local/'before.xml');(local/'before.xml').chmod(0o600)
    before=(local/'before.xml').read_bytes();blob=empty_preferences(before);(local/'deployed.xml').write_bytes(blob);(local/'deployed.xml').chmod(0o600)
    remote.upload(local/'deployed.xml',target+'/empty.xml');remote.python("from pathlib import Path\nPath(PAYLOAD).chmod(0o600)",target+'/empty.xml')
    temporary='/data/local/tmp/history-empty-'+stamp+'.xml'
    remote.hdc(['file','send',target+'/empty.xml',temporary])
    remote.hdc(['shell',f'cp {temporary} {PREFERENCES} && chown {uid}:{gid} {PREFERENCES} && chmod 660 {PREFERENCES}'])
    remote.python("import subprocess,hashlib\nfrom pathlib import Path\np=Path(PAYLOAD['root'])/'readback.xml'\nsubprocess.run(['hdc','file','recv',PAYLOAD['preferences'],str(p)],check=True,capture_output=True,timeout=30)\np.chmod(0o600)\nassert hashlib.sha256(p.read_bytes()).hexdigest()==PAYLOAD['sha256']",{'root':target,'preferences':PREFERENCES,'sha256':hashlib.sha256(blob).hexdigest()})
    remote.hdc(['shell','rm -f '+temporary])
    result={'case':CASE,'variant':variant,'preferences':PREFERENCES,'preparation_dir':str(local),
            'sha256':IDENTITY,'before_sha256':hashlib.sha256(before).hexdigest(),'deployed_sha256':hashlib.sha256(blob).hexdigest(),
            'remote_backup':target+'/before.xml','installation_verified':True,'functional_read_verified':False,
            'method':'empty ordinary native historyStore; all authentication and other stores unchanged'}
    verify(result);return result
