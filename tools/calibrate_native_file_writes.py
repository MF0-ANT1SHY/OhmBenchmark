#!/usr/bin/env python3
"""Run the own-process HMFS calibration from the repository root.

Compile tools/native_file_write_probe.c with the OpenHarmony aarch64 SDK, then
pass its ELF with --binary and a new proof path with --output. No app is opened.
"""
import argparse,json,sys,uuid,hashlib,textwrap
from pathlib import Path
sys.path.insert(0,'tools')
from remote_device import Remote
from native_file_writes import returned_writes,verify_retention
def main():
    parser=argparse.ArgumentParser(description='Calibrate standalone native writes and complete per-CPU trace retention; never attaches to an app.')
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('preserve the previous native calibration')
    if args.binary.read_bytes()[:4]!=b'\x7fELF':raise ValueError('compiled standalone ELF probe required')
    r=Remote();token=uuid.uuid4().hex;root='/home/research/ohm-clean/hmfs-retention/'+token;device='/data/local/tmp/ohm-file-write-probe-'+token;data=device+'d'
    for module in ('native_file_trace.py','native_file_writes.py','native_trace_record.py','rss_refresh_progress.py'):r.upload(Path('tools')/module,'/home/research/ohm-clean/tools/'+module)
    r.upload(args.binary,root+'/probe')
    code='''import json,sys,subprocess
    from pathlib import Path
    sys.path.insert(0,'/home/research/ohm-clean/tools')
    from native_file_trace import record
    root=Path(PAYLOAD['root']);root.chmod(0o700)
    def shell(cmd):
     p=subprocess.run(['hdc','shell',cmd],capture_output=True,text=True,timeout=90)
     if p.returncode:raise RuntimeError(p.stdout+p.stderr)
     return p.stdout
    subprocess.run(['hdc','file','send',str(root/'probe'),PAYLOAD['device']],check=True,capture_output=True,timeout=30);shell('chmod 700 '+PAYLOAD['device'])
    def action():return json.loads(shell(PAYLOAD['device']+' '+PAYLOAD['data']).strip())
    try:
     result=record(shell,action,root/'capture');print(json.dumps({'status':result['status'],'error':result.get('error')}))
     subprocess.run(['hdc','file','recv',PAYLOAD['data'],str(root/'written.bin')],check=True,capture_output=True,timeout=30)
    finally:shell('rm -f '+PAYLOAD['device']+' '+PAYLOAD['data'])
    '''
    code=textwrap.dedent('    '+code)
    print(r.python(code,{'root':root,'device':device,'data':data},timeout=300),flush=True);local=Path('artifacts/native-file-write-retention-calibration')/token;local.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name in ('capture/capture.json','capture/trace.txt','written.bin'):r.download(root+'/'+name,local/name)
    for path in local.rglob('*'):path.chmod(0o700 if path.is_dir() else 0o600)
    d=json.loads((local/'capture/capture.json').read_text());assert d['status']=='NATIVE_FILE_TRACE_CAPTURED',d.get('error');raw=(local/'capture/trace.txt').read_text();ret=verify_retention(raw,d['token'],d['cpus_before']);p=d['action'];dev=p['dev'];w=returned_writes(raw,[p['pid']],[(dev>>20,dev&((1<<20)-1),p['ino'])]);assert p['passed'] and w['returned_bytes']==31 and w['completed_writes']==2 and (local/'written.bin').read_bytes()==b'native-write-calibration1234567'
    proof={'status':'OWN_PROCESS_HMFS_WRITE_AND_ALL_CPU_RETENTION_CALIBRATED','raw_artifacts':str(local),'capture_sha256':hashlib.sha256((local/'capture/capture.json').read_bytes()).hexdigest(),'trace_sha256':d['trace_sha256'],'retention':ret,'writes':w,'app_attached':False,'app_write_volume_proven':False,'performance_accepted':False,'tracing_on_after':d['tracing_on_after'],'events_enabled_after':d['events_enabled_after'],'buffer_size_restored':d['buffer_size_after']}
    args.output.write_text(json.dumps(proof,indent=2)+'\n');print(proof['status'],flush=True)


if __name__ == '__main__':
    main()
