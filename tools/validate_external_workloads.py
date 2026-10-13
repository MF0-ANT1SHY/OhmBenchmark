#!/usr/bin/env python3
"""Validate actual UI actions on each clean variant, with archived device evidence.

This records workload execution, never a CPU/memory improvement verdict. Browser
fixtures are prepared externally for each variant, keeping the comparison data
identical even after destructive actions such as clearing history.
"""
import argparse
import hashlib
import json
import subprocess
import sqlite3
import shlex
import time
import re
from pathlib import Path

from install_sqlite_fixture import install as install_fixture
from remote_device import Remote
from seed_local_songs import deploy as deploy_songs
from bundled_audio_fixture import for_case as packaged_audio
from playback_progress import check_progress
from install_search_history_fixture import install as install_search_history
from music_service_fixture import prepare as prepare_music_service, same_instance
from bundled_font_fixture import for_case as packaged_fonts
from page_lifecycle import verify_reconstructions
from reader_data_fixture import prepare as prepare_reader, finish as finish_reader
from rss_refresh_progress import verify_observation
from jingmo_import_fixture import prepare as prepare_import, finish as finish_import, verify_state

ROOT = Path(__file__).resolve().parents[1]


def validate(remote, case, variant, browser_fixture=None, local_song_fixture=None, poem_fixture=None, bundled_audio=False, search_history_fixture=None, preferences_path=None, music_service=False, bundled_fonts=False, reader_fixture=None, poem_import_fixture=None):
    cid = case['id']
    folder = ROOT / 'artifacts/clean' / cid / variant
    signed = json.loads((folder / 'sign.json').read_text())
    plan_path = ROOT / 'cases' / cid / case['testcase']['workload']
    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    result = {'case':cid, 'variant':variant, 'signed_sha256':signed['audit']['sha256'],
              'plan_sha256':plan_hash, 'status':'FAIL', 'performance_verified':False}
    try:
        if sum(p is not None for p in (browser_fixture,local_song_fixture,poem_fixture,search_history_fixture,reader_fixture,poem_import_fixture))+int(bundled_audio)+int(music_service)+int(bundled_fonts)>1:
            raise ValueError('only one fixture may be supplied')
        if bundled_audio:
            result['fixture']=packaged_audio(ROOT,case,variant,signed)
        if bundled_fonts:
            result['fixture']=packaged_fonts(ROOT,case,variant,signed)
        if music_service:
            result['fixture']=prepare_music_service(remote,case)
        if local_song_fixture and case['host_app']['bundle_name']!='cc.chenlvin.cloudmusic':
            raise ValueError('local song fixture provided to a different app')
        if poem_fixture and case['host_app']['bundle_name']!='com.hefengbao.jingmo.hw':
            raise ValueError('poetry fixture provided to a different app')
        remote.python("from pathlib import Path\nimport hashlib\n"
                      f"assert hashlib.sha256(Path({signed['signed_hap']!r}).read_bytes()).hexdigest()=={signed['audit']['sha256']!r}", timeout=300)
        output = remote.hdc(['install','-r',signed['signed_hap']], timeout=180)
        if 'install bundle successfully' not in output:
            raise RuntimeError(output)
        if browser_fixture and cid.startswith('browser_'):
            result['fixture'] = install_fixture(remote, case['host_app']['bundle_name'],
                                                case['testcase']['module'], 'Histories.db', browser_fixture)
            result['fixture']['sha256'] = hashlib.sha256(browser_fixture.read_bytes()).hexdigest()
        if local_song_fixture:
            result['fixture']=deploy_songs(local_song_fixture,remote.host)
            result['fixture']['sha256']=result['fixture']['fixture_sha256']
        if poem_fixture:
            result['fixture']=install_fixture(remote,case['host_app']['bundle_name'],case['testcase']['module'],'jingmo.db',poem_fixture)
            result['fixture']['sha256']=hashlib.sha256(poem_fixture.read_bytes()).hexdigest()
        if search_history_fixture:
            result['fixture']=install_search_history(remote,case,variant,search_history_fixture,preferences_path or '')
        if reader_fixture:
            result['fixture']=prepare_reader(remote,case,reader_fixture)
        if poem_import_fixture:
            result['fixture']=prepare_import(remote,case,poem_import_fixture)
        destination = f'/home/research/ohm-clean/{cid}/{variant}/workload-plan.json'
        remote.upload(plan_path, destination)
        code = """import hashlib,json,subprocess,sys,time,traceback
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools')
from ui_driver import UI
def shell(command):
 p=subprocess.run(['hdc','shell',command],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
"""
        code += f"plan_path=Path({destination!r});plan=json.loads(plan_path.read_text())\n"
        code += f"assert hashlib.sha256(plan_path.read_bytes()).hexdigest()=={plan_hash!r}\n"
        code += "ui=UI(shell,plan['bundle'],plan['ability'])\nphases={}\n"
        if poem_import_fixture:
            for module in ('jingmo_import_fixture.py','jingmo_data_service.py','rss_service_fixture.py','rss_data_service.py','rss_dataset.py','install_sqlite_fixture.py','remote_device.py'):
                remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
            code += "from jingmo_import_fixture import complete_import\n"
        if reader_fixture:
            remote.upload(ROOT/'tools/rss_refresh_progress.py','/home/research/ohm-clean/tools/rss_refresh_progress.py')
            code += "from rss_refresh_progress import read_state,complete_refresh\n"
        if cid=='sepweather_font_register_per_page':
            for module in ('page_lifecycle.py','system_pss.py'):
                remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
            code += "from page_lifecycle import observe_page\npage_observations=[]\noriginal_find=ui.find\n"
            code += "def observe_find(selector,timeout=15):\n"
            code += " node=original_find(selector,timeout)\n"
            code += " if selector.get('id')=='AddAddressBtn':page_observations.append(observe_page(shell,plan['bundle'],node))\n"
            code += " return node\nui.find=observe_find\n"
        if cid=='jingmo_random_poem_orderby_random':
            code += "import re\nobserved_poem_titles=[]\noriginal_find=ui.find\n"
            code += "def observe_find(selector,timeout=15):\n"
            code += " node=original_find(selector,timeout)\n"
            code += " title=str(node.get('text',''))\n"
            code += " if re.fullmatch(r'山水诗 [1-9][0-9]*',title):observed_poem_titles.append(title)\n"
            code += " return node\nui.find=observe_find\n"
        code += "ui.run([{'op':'stop'},{'op':'launch'}])\n"
        code += "try:\n"
        code += " for phase in ['setup','measured','verify']:\n"
        code += "  started=time.monotonic()\n  ui.run(plan[phase])\n"
        code += "  phases[phase]={'elapsed_s':time.monotonic()-started,'layout':ui.layout()}\n"
        if reader_fixture:
            code += "  if phase=='setup':reader_before=read_state(shell)\n"
        code += " result={'phases':phases,'status':'PASS'}\n"
        if poem_import_fixture:
            code += " result['poem_import_state']=complete_import(ui)\n"
        if reader_fixture:
            code += " result['reader_refresh']=complete_refresh(ui,reader_before)\n"
        code += "except Exception as exc:\n"
        code += " result={'phases':phases,'status':'FAIL','error':str(exc)}\n"
        code += " try:result['failure_layout']=ui.layout()\n except Exception:pass\n"
        if cid=='jingmo_random_poem_orderby_random':
            code += "result['observed_poem_titles']=observed_poem_titles\n"
        if cid=='sepweather_font_register_per_page':
            code += "result['page_observations']=page_observations\n"
        code += "plan_path.with_name('workload-device.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))\n"
        remote.python(code, timeout=600)
        remote.download(str(Path(destination).with_name('workload-device.json')), folder / 'workload-device.json')
        device = json.loads((folder / 'workload-device.json').read_text())
        if device['status'] != 'PASS':
            raise RuntimeError(device['error'])
        result['phase_elapsed_s'] = {p:r['elapsed_s'] for p,r in device['phases'].items()}
        if poem_import_fixture:
            verify_state(device['poem_import_state'],True)
            result['fixture_after']=finish_import(remote,result['fixture'])
            result['functional_check']='all 5000 full ordinary poetry records imported from the configured source'
        if reader_fixture:
            result['reader_refresh']=verify_observation(device['reader_refresh'])
            result['fixture_after']=finish_reader(remote,case,result['fixture'])
            result['functional_check']='all ordinary RSS articles verified and all ten feeds refreshed through the existing UI shortcut'
        if cid=='sepweather_font_register_per_page':
            result['page_reconstructions']=verify_reconstructions(device['page_observations'],case['host_app']['bundle_name'])
        if music_service:
            after=prepare_music_service(remote,case)
            same_instance(result['fixture'],after)
            result['fixture_after']=after
            from ui_driver import UI
            texts={n.get('text','') for n in UI.nodes(device['phases']['verify']['layout'])
                   if n.get('bundleName')==case['host_app']['bundle_name']}
            titles={t for t in texts if re.fullmatch(r'Track [1-9][0-9]*',t)}
            expected_artists=', '.join(f'Artist {i}' for i in range(1,13))
            if (not titles or any(int(t.split()[1])>10000 for t in titles)
                    or expected_artists not in texts):
                raise RuntimeError('normal song rows do not match the ordinary music catalogue')
            result['functional_check']='normal song titles and artist lines match the ordinary music catalogue'
            result['observed_titles']=sorted(titles)
        if search_history_fixture:
            from ui_driver import UI
            events=json.loads((search_history_fixture/'submissions.json').read_text())
            expected=set(events if variant=='unfixed' else list(dict.fromkeys(reversed(events)))[:20])
            texts={n.get('text') for n in UI.nodes(device['phases']['setup']['layout'])
                   if n.get('bundleName')==case['host_app']['bundle_name']}
            if not expected.intersection(texts):
                raise RuntimeError('normal search-history UI did not read the deployed preference fixture')
            result['fixture']['functional_read_verified']=True
            result['functional_check']='normal history UI displays entries from the ordinary preference fixture'
        if cid=='ytmusic_current_playing_timeupdate':
            # The snapshots bracket measured idle playback. Dump latency is
            # bounded by the progress check's tolerance; a title alone is not proof.
            result['playback_progress']=check_progress(
                device['phases']['setup']['layout'],device['phases']['measured']['layout'],
                case['host_app']['bundle_name'],result['phase_elapsed_s']['measured'])
        if cid=='jingmo_random_poem_orderby_random':
            if not poem_fixture:
                raise RuntimeError('random-poem validation requires a known fixture')
            from ui_driver import UI
            texts={str(n.get('text','')) for n in UI.nodes(device['phases']['verify']['layout'])
                   if n.get('bundleName')==case['host_app']['bundle_name']}
            with sqlite3.connect(f'file:{poem_fixture.resolve()}?mode=ro',uri=True) as fixture_db:
                rows=fixture_db.execute('SELECT title,content FROM classicalliterature_classicpoem WHERE title IN ('+
                    ','.join('?' for _ in texts)+')',list(texts)).fetchall()
            if not any(title in texts and content in texts for title,content in rows):
                raise RuntimeError('displayed poetry does not match the ordinary database fixture')
            titles=device.get('observed_poem_titles',[])
            if len(titles)<21 or len(set(titles))<2:
                raise RuntimeError('repeated refreshes did not produce observable poetry updates')
            result['functional_check']='displayed poetry title and content match the database fixture'
            result['observed_refresh_titles']=titles
        if cid == 'browser_history_delete_no_transaction':
            db = '/data/app/el2/100/database/com.example.nanvision/entry/rdb/Histories.db'
            if not browser_fixture:
                raise RuntimeError('clear-history validation requires a known fixture')
            with sqlite3.connect(f'file:{browser_fixture.resolve()}?mode=ro',uri=True) as fixture_db:
                tables=[r[0] for r in fixture_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='date_table' OR name LIKE 'history_%')")]
            if not tables or any(not re.fullmatch(r'date_table|history_[0-9_]+',t) for t in tables):
                raise RuntimeError('unexpected history fixture schema')
            sql='SELECT '+'+'.join(f'(SELECT COUNT(*) FROM {t})' for t in tables)+';'
            deadline=time.monotonic()+120
            while True:
                remaining = remote.hdc(['shell', f'sqlite3 {db} {shlex.quote(sql)}']).strip()
                if remaining=='0':break
                if not remaining.isdigit() or time.monotonic()>deadline:
                    raise RuntimeError(f'clear-history UI left database rows: {remaining}')
                time.sleep(.1)
            result['functional_check'] = 'all history rows and dates cleared through the production UI'
            result['cleared_tables'] = len(tables)
        result['status'] = device['status']
        result['capture_duration_required_s'] = round(result['phase_elapsed_s']['measured'] + 5)
    except Exception as exc:
        result['error'] = str(exc)
    (folder / 'workload.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(f"{cid}/{variant}: {result['status']} {result.get('error','')}", flush=True)
    return result['status']=='PASS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases',nargs='+')
    parser.add_argument('--remote',default='cityuPC')
    fixtures=parser.add_mutually_exclusive_group()
    fixtures.add_argument('--browser-fixture',type=Path)
    fixtures.add_argument('--local-song-fixture',type=Path)
    fixtures.add_argument('--poem-fixture',type=Path)
    fixtures.add_argument('--bundled-audio',action='store_true')
    fixtures.add_argument('--search-history-fixture',type=Path)
    fixtures.add_argument('--music-service',action='store_true')
    fixtures.add_argument('--bundled-fonts',action='store_true')
    fixtures.add_argument('--reader-fixture',type=Path)
    fixtures.add_argument('--poem-import-fixture',type=Path)
    parser.add_argument('--preferences-path',help='actual initialized historyStore file; discover through normal app use')
    args=parser.parse_args()
    remote=Remote(args.remote)
    remote.upload(ROOT/'tools/ui_driver.py','/home/research/ohm-clean/tools/ui_driver.py')
    failed=False
    for cid in args.cases:
        case=json.loads((ROOT/'cases'/cid/'case.json').read_text())
        for variant in ('unfixed','fixed'):
            failed |= not validate(remote,case,variant,args.browser_fixture,args.local_song_fixture,args.poem_fixture,args.bundled_audio,args.search_history_fixture,args.preferences_path,args.music_service,args.bundled_fonts,args.reader_fixture,args.poem_import_fixture)
    return int(failed)


if __name__=='__main__':
    raise SystemExit(main())
