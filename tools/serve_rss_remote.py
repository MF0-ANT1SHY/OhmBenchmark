#!/usr/bin/env python3
"""Keep an existing ordinary RSS catalogue in a bounded workstation lease."""
import argparse
import hashlib
from pathlib import Path

from remote_device import Remote
from rss_data_service import Catalogue
from rss_dataset import normalize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remote', default='cityuPC')
    parser.add_argument('--duration', type=int, default=7200)
    parser.add_argument('--body-bytes', type=int, default=256)
    args = parser.parse_args()
    if not 60 <= args.duration <= 7200:
        raise ValueError('lease duration must be 60 to 7200 seconds')
    dataset = normalize({'body_bytes': args.body_bytes})
    source_hash = hashlib.sha256(Path(__file__).with_name('rss_data_service.py').read_bytes()).hexdigest()
    expected = hashlib.sha256(Catalogue('http://127.0.0.1:18491', body_bytes=args.body_bytes).feed(1)).hexdigest()
    code = """import hashlib,json,subprocess,time,urllib.request
from pathlib import Path
base=Path('/home/research/ohm-clean/services/rss')
record=json.loads((base/'process.json').read_text())
assert record['base_url']=='http://127.0.0.1:18491'
assert record['feeds']==10 and record['articles_per_feed']==100
assert record.get('body_bytes',32768)==PAYLOAD['body_bytes']
assert hashlib.sha256(Path(record['source']).read_bytes()).hexdigest()==PAYLOAD['source_sha256']
proc=Path('/proc')/str(record['pid'])
assert not proc.exists() or record['source'].encode() not in proc.joinpath('cmdline').read_bytes(),'owned RSS source still live; do not duplicate'
with (base/'foreground-service.log').open('ab') as log:
 child=subprocess.Popen(['python3',record['source'],'--port','18491','--feeds','10','--articles','100','--body-bytes',str(PAYLOAD['body_bytes'])],stdout=log,stderr=subprocess.STDOUT)
 try:
  for attempt in range(50):
   if child.poll() is not None:raise RuntimeError('RSS bind failed; unknown existing listener not touched')
   try:
    with urllib.request.urlopen(record['base_url']+'/feeds/1.xml',timeout=2) as response:blob=response.read()
    assert hashlib.sha256(blob).hexdigest()==PAYLOAD['response_sha256']
    break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('ordinary RSS source not ready')
  record['pid']=child.pid;record['hosting']='foreground SSH lease'
  (base/'process.json').write_text(json.dumps(record,indent=2))
  print('Owned ordinary RSS source ready',flush=True)
  child.wait(timeout=PAYLOAD['duration'])
 finally:
  if child.poll() is None:child.terminate();child.wait(timeout=10)
"""
    print(Remote(args.remote).python(code, {'source_sha256': source_hash,
          'response_sha256': expected, 'body_bytes': dataset['body_bytes'],
          'duration': args.duration}, timeout=args.duration+50), flush=True)


if __name__ == '__main__':
    main()
