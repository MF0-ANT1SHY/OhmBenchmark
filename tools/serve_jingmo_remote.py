#!/usr/bin/env python3
import sys,hashlib,argparse
from pathlib import Path
from remote_device import Remote
parser=argparse.ArgumentParser(description='Host the ordinary poetry source in a bounded foreground SSH lease; no app code is changed.');parser.add_argument('--remote',default='cityuPC');parser.add_argument('--duration',type=int,default=3300);args=parser.parse_args();assert 60<=args.duration<=7200
r=Remote(args.remote);digest=hashlib.sha256(Path(__file__).with_name('jingmo_data_service.py').read_bytes()).hexdigest()
code="""from pathlib import Path
import json,hashlib,subprocess,time,urllib.request
base=Path('/home/research/ohm-clean/services/jingmo');old=json.loads((base/'process.json').read_text())
assert hashlib.sha256(Path(old['source']).read_bytes()).hexdigest()==PAYLOAD['source_sha256']
proc=Path('/proc')/str(old['pid'])
assert not proc.exists() or old['source'].encode() not in proc.joinpath('cmdline').read_bytes(),'owned source still live; do not duplicate'
log=(base/'foreground-service.log').open('ab');child=subprocess.Popen(['python3',old['source'],'--port','18492','--count','5000'],stdout=log,stderr=subprocess.STDOUT)
try:
 for i in range(50):
  if child.poll() is not None:raise RuntimeError('source bind failed; unknown existing listener not touched')
  try:
   with urllib.request.urlopen('http://127.0.0.1:18492/api/classicalliterature_classicpoem1.json',timeout=2) as response:blob=response.read()
   assert hashlib.sha256(blob).hexdigest()==old['response_sha256']
   break
  except OSError:time.sleep(.2)
 else:raise RuntimeError('source not ready')
 old['pid']=child.pid;old['hosting']='foreground SSH lease';(base/'process.json').write_text(json.dumps(old,indent=2))
 print('Owned ordinary poetry source ready',flush=True)
 child.wait(timeout=PAYLOAD['duration'])
finally:
 if child.poll() is None:child.terminate();child.wait(timeout=10)
"""
print(r.python(code,{'source_sha256':digest,'duration':args.duration},timeout=args.duration+50),flush=True)
