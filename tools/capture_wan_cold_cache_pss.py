#!/usr/bin/env python3
"""Supplementary offline cold-cache PSS, not the full load-more case oracle."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import time

from remote_device import Remote
from install_wan_home_cache_fixture import install, fixture_state
from system_pss import capture_window, verify_window

ROOT = Path(__file__).resolve().parents[1]
CASE = 'wanharmony_persisted_home_list_growth'
BUNDLE = 'org.example.wan.ohos'
DEVICE = '/data/app/el2/100/base/org.example.wan.ohos/haps/entry/files/persistent_storage'


def capture(remote, variant, number, fixture):
    if variant not in ('unfixed', 'fixed') or number not in (1, 2, 3):
        raise ValueError('three paired cold-cache trials required')
    receipt, _ = fixture_state(fixture)
    articles = json.loads((fixture/'articles.json').read_text())
    folder = ROOT/'artifacts/clean'/CASE/variant
    destination = folder/'cold-cache-pss'/f'round-{number}'
    if destination.exists():
        raise FileExistsError('never overwrite an existing supplementary trial')
    signed = json.loads((folder/'sign.json').read_text())
    ui_proof = json.loads((ROOT/'validation/wan-home-cold-cache-ui.json').read_text())
    if (ui_proof['variants'][variant]['status'] != 'PASS'
            or ui_proof['variants'][variant]['signed_sha256'] != signed['audit']['sha256']
            or ui_proof['variants'][variant]['deployment']['sha256'] != receipt['fixture_sha256']):
        raise ValueError('matching ordinary cold-cache UI input is not proven')
    code = '''import subprocess,hashlib
from pathlib import Path
for name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):
 p=subprocess.run(['hdc','shell','pidof '+name],capture_output=True,text=True);assert not p.stdout.strip()
p=subprocess.run(['hdc','shell','cat /sys/kernel/tracing/tracing_on'],capture_output=True,text=True);assert p.stdout.strip()=='0'
p=subprocess.run(['hdc','shell','ip route show'],capture_output=True,text=True);assert not p.stdout.strip(),'offline supplement cannot replace online loading'
assert hashlib.sha256(Path(PAYLOAD['hap']).read_bytes()).hexdigest()==PAYLOAD['sha']
for bundle in PAYLOAD['bundles']:
 subprocess.run(['hdc','shell','aa force-stop '+bundle],capture_output=True,check=True)
p=subprocess.run(['hdc','install','-r',PAYLOAD['hap']],capture_output=True,text=True,timeout=180);assert 'install bundle successfully' in p.stdout
'''
    bundles = sorted({json.loads(p.read_text())['host_app']['bundle_name'] for p in (ROOT/'cases').glob('*/case.json')})
    remote.python(code, {'hap': signed['signed_hap'], 'sha': signed['audit']['sha256'], 'bundles': bundles}, timeout=240)
    prepared = install(remote, json.loads((ROOT/'cases'/CASE/'case.json').read_text()), fixture, DEVICE)
    remote.upload(ROOT/'tools/ui_driver.py', '/home/research/ohm-clean/tools/ui_driver.py')
    remote_root = f'/home/research/ohm-clean/{CASE}/{variant}/cold-cache-pss/round-{number}'
    code = '''import json,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools');from ui_driver import UI
def shell(c):
 p=subprocess.run(['hdc','shell',c],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
ui=UI(shell,'org.example.wan.ohos');ui.run([{'op':'stop'},{'op':'launch'}])
ui.find({'text':'首页','match':'exact'},120);ui.find({'text':PAYLOAD['title'],'match':'exact'},120)
root=Path(PAYLOAD['root']);root.mkdir(parents=True,exist_ok=True)
(root/'layout-before.json').write_text(json.dumps(ui.layout(),ensure_ascii=False))
print(shell('pidof org.example.wan.ohos').strip())
'''
    pid = remote.python(code, {'title': html.unescape(articles[0]['title']), 'root': remote_root}, timeout=360).strip()
    if not pid.isdigit():
        raise ValueError('one real main app process required')
    result = capture_window(remote, int(pid), BUNDLE, lambda: time.sleep(10), interval_s=2)
    verify_window(result, BUNDLE)
    code = '''import subprocess,json,xml.etree.ElementTree as ET
from pathlib import Path
p=subprocess.run(['hdc','shell','cat '+PAYLOAD['device']],capture_output=True,text=True,check=True)
root=ET.fromstring(p.stdout);values={n.attrib['key']:json.loads(n.text) for n in root if n.attrib.get('key') in ('homeList','homeListCache')}
assert values['homeList']==PAYLOAD['articles'] and values['homeListCache']==PAYLOAD['articles'][:20]
Path(PAYLOAD['root']+'/cache-after.json').write_text(json.dumps(values,ensure_ascii=False))
print('PRESERVED')
'''
    assert remote.python(code, {'device': DEVICE, 'articles': articles, 'root': remote_root}).strip() == 'PRESERVED'
    result.update(case=CASE, variant=variant, round=number, status='SUPPLEMENT_CAPTURED',
                  metric='app_pss_bytes', signed_sha256=signed['audit']['sha256'],
                  fixture_sha256=prepared['sha256'], preparation=prepared,
                  supplementary_only=True, performance_accepted=False,
                  network_load_more_verified=False,
                  method='final absolute kernel PSS after ten seconds displaying ordinary offline cold cache')
    destination.mkdir(parents=True)
    (destination/'capture.json').write_text(json.dumps(result,indent=2)+'\n')
    remote.download(remote_root+'/layout-before.json', destination/'layout-before.json')
    remote.download(remote_root+'/cache-after.json', destination/'cache-after.json')
    print(f'{variant}/round-{number}: supplementary final PSS {result["app_pss_bytes"]}', flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('variant', choices=['unfixed', 'fixed'])
    p.add_argument('--round', type=int, choices=[1, 2, 3], required=True)
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--remote', default='cityuPC')
    a = p.parse_args()
    capture(Remote(a.remote), a.variant, a.round, a.fixture)
