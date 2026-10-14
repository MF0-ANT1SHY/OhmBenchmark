#!/usr/bin/env python3
"""Collect generic system PMU samples across an external UI workload.

No probes or synchronization code are placed in the app. This emits raw capture
evidence only; it does not declare that a case meets its performance oracle.
"""
import argparse
import hashlib
import json
import uuid
from pathlib import Path

from install_sqlite_fixture import install as install_fixture
from remote_device import Remote
from seed_local_songs import deploy as deploy_songs
from bundled_audio_fixture import for_case as packaged_audio
from music_service_fixture import prepare as prepare_music_service, same_instance
from bundled_font_fixture import for_case as packaged_fonts
from reader_data_fixture import prepare as prepare_reader, finish as finish_reader
from jingmo_import_fixture import prepare as prepare_import, finish as finish_import
from jingmo_sync_fixture import prepare as prepare_sync, finish as finish_sync

ROOT = Path(__file__).resolve().parents[1]


def capture(remote, case, variant, round_number, fixture=None, local_song_fixture=None, poem_fixture=None, bundled_audio=False, music_service=False, bundled_fonts=False, reader_fixture=None, poem_import_fixture=None, poem_sync_fixture=None):
    cid = case['id']
    if sum(p is not None for p in (fixture,local_song_fixture,poem_fixture,reader_fixture,poem_import_fixture,poem_sync_fixture))+int(bundled_audio)+int(music_service)+int(bundled_fonts)>1:
        raise ValueError('only one fixture may be supplied')
    if local_song_fixture and case['host_app']['bundle_name']!='cc.chenlvin.cloudmusic':
        raise ValueError('local song fixture provided to a different app')
    if poem_fixture and case['host_app']['bundle_name']!='com.hefengbao.jingmo.hw':
        raise ValueError('poetry fixture provided to a different app')
    fixture_hash=None
    service_fixture=None
    folder = ROOT/'artifacts/clean'/cid/variant
    sign = json.loads((folder/'sign.json').read_text())
    if bundled_audio:
        fixture_hash=packaged_audio(ROOT,case,variant,sign)['sha256']
    if bundled_fonts:
        fixture_hash=packaged_fonts(ROOT,case,variant,sign)['sha256']
    if music_service:
        service_fixture=prepare_music_service(remote,case)
        fixture_hash=service_fixture['sha256']
    plan_file = ROOT/'cases'/cid/case['testcase']['workload']
    plan_hash = hashlib.sha256(plan_file.read_bytes()).hexdigest()
    output = folder/'cpu-captures'/f'round-{round_number}'
    output.mkdir(parents=True,exist_ok=True)
    remote_base = f'/home/research/ohm-clean/{cid}/{variant}/cpu-captures/round-{round_number}'
    remote_plan = remote_base+'/plan.json'
    # Isolate this trial from the other benchmark apps left running by smoke
    # checks. Do not stop unrelated applications installed on the device.
    bundles=sorted({json.loads(p.read_text())['host_app']['bundle_name']
                    for p in (ROOT/'cases').glob('*/case.json')})
    for bundle in bundles:
        remote.hdc(['shell','aa force-stop '+bundle])
    response = remote.hdc(['install','-r',sign['signed_hap']],timeout=180)
    if 'install bundle successfully' not in response:
        raise RuntimeError(response)
    if fixture:
        if not cid.startswith('browser_'):
            raise ValueError('browser fixture provided to a different app')
        install_fixture(remote,case['host_app']['bundle_name'],case['testcase']['module'],'Histories.db',fixture)
        fixture_hash=hashlib.sha256(fixture.read_bytes()).hexdigest()
    if local_song_fixture:
        fixture_hash=deploy_songs(local_song_fixture,remote.host)['fixture_sha256']
    if poem_fixture:
        install_fixture(remote,case['host_app']['bundle_name'],case['testcase']['module'],'jingmo.db',poem_fixture)
        fixture_hash=hashlib.sha256(poem_fixture.read_bytes()).hexdigest()
    if reader_fixture:
        reader_before=prepare_reader(remote,case,reader_fixture)
        fixture_hash=reader_before['sha256']
    if poem_import_fixture:
        import_before=prepare_import(remote,case,poem_import_fixture)
        fixture_hash=import_before['sha256']
    if poem_sync_fixture:
        sync_before=prepare_sync(remote,case,poem_sync_fixture)
        fixture_hash=sync_before['sha256']
    remote.upload(plan_file,remote_plan)
    code = """import hashlib,json,subprocess,sys,time,traceback
from pathlib import Path
sys.path.insert(0,'/home/research/ohm-clean/tools')
from ui_driver import UI
def shell(command):
 p=subprocess.run(['hdc','shell',command],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
"""
    code += f"root=Path({remote_base!r});plan_file=Path({remote_plan!r})\n"
    code += f"assert hashlib.sha256(plan_file.read_bytes()).hexdigest()=={plan_hash!r}\n"
    code += f"assert hashlib.sha256(Path({sign['signed_hap']!r}).read_bytes()).hexdigest()=={sign['audit']['sha256']!r}\n"
    code += "plan=json.loads(plan_file.read_text());ui=UI(shell,plan['bundle'],plan['ability'])\n"
    if poem_import_fixture or poem_sync_fixture:
        for module in ('jingmo_import_fixture.py','jingmo_data_service.py','rss_service_fixture.py','rss_data_service.py','rss_dataset.py','install_sqlite_fixture.py','remote_device.py'):
            remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
        code += "from jingmo_import_fixture import complete_import,read_state,verify_state\n"
    if cid=='sepweather_font_register_per_page':
        for module in ('page_lifecycle.py','system_pss.py'):
            remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
        code += "from page_lifecycle import observe_page,verify_reconstructions\npage_observations=[]\noriginal_find=ui.find\n"
        code += "def observe_find(selector,timeout=15):\n"
        code += " node=original_find(selector,timeout)\n"
        code += " if selector.get('id')=='AddAddressBtn':page_observations.append(observe_page(shell,plan['bundle'],node))\n"
        code += " return node\nui.find=observe_find\n"
    code += "ui.run([{'op':'stop'},{'op':'launch'}]);ui.run(plan['setup'])\n"
    if reader_fixture:
        remote.upload(ROOT/'tools/rss_refresh_progress.py','/home/research/ohm-clean/tools/rss_refresh_progress.py')
        code += "from rss_refresh_progress import read_state,complete_refresh\nreader_before=read_state(shell)\n"
    if cid=='ytmusic_current_playing_timeupdate':
        remote.upload(ROOT/'tools/playback_progress.py','/home/research/ohm-clean/tools/playback_progress.py')
        code += "from playback_progress import check_progress\n"
        code += "playback_start_layout=ui.layout();playback_start_time=time.monotonic()\n"
    token=uuid.uuid4().hex
    code += f"device_file='/data/local/tmp/profile-{token}.data'\n"
    code += "assert not shell('pidof hiperf').strip(),'another profiler session is active'\n"
    code += "record={'status':'FAIL','event':'hw-instructions'}\n"
    code += "prepared_ok=False\n"
    code += "try:\n"
    code += " prepared=shell('hiperf record --control prepare -a --exclude-hiperf --cpu-limit 100 -f 1000 -e hw-instructions --call-stack dwarf --clockid boottime --kernel-callchain -m 1024 -o '+device_file)\n"
    code += " record['prepare_output']=prepared\n"
    code += " if 'fail' in prepared.lower() or 'error' in prepared.lower():raise RuntimeError(prepared)\n"
    code += " prepared_ok=True\n"
    code += " record['start_output']=shell('hiperf record --control start')\n"
    code += " if 'fail' in record['start_output'].lower() or 'error' in record['start_output'].lower():raise RuntimeError(record['start_output'])\n"
    code += " record['action_start_monotonic']=time.monotonic()\n"
    code += " ui.run(plan['measured']);ui.run(plan['verify'])\n"
    if poem_import_fixture:
        code += " record['poem_import_state']=complete_import(ui)\n"
    if poem_sync_fixture:
        code += " record['poem_sync_state']=read_state(shell);verify_state(record['poem_sync_state'],True)\n"
    if reader_fixture:
        code += " record['reader_refresh']=complete_refresh(ui,reader_before)\n"
    if cid=='sepweather_font_register_per_page':
        code += " record['page_observations']=page_observations\n"
        code += " record['page_reconstructions']=verify_reconstructions(page_observations,plan['bundle'])\n"
    if cid=='ytmusic_current_playing_timeupdate':
        code += " playback_end_layout=ui.layout();playback_elapsed=time.monotonic()-playback_start_time\n"
        code += " record['playback_observation']={'start_layout':playback_start_layout,'end_layout':playback_end_layout,'elapsed_s':playback_elapsed}\n"
        code += " record['playback_progress']=check_progress(playback_start_layout,playback_end_layout,plan['bundle'],playback_elapsed)\n"
    if cid=='browser_history_delete_no_transaction':
        # The button returns before its async database work completes. This is a
        # private evaluator check, outside the app and excluded from app attribution.
        code += " deadline=time.monotonic()+120\n"
        code += " while True:\n"
        code += "  remaining=shell(\"sqlite3 /data/app/el2/100/database/com.example.nanvision/entry/rdb/Histories.db 'SELECT COUNT(*) FROM date_table;'\").strip()\n"
        code += "  if remaining=='0':break\n"
        code += "  if not remaining.isdigit():raise RuntimeError('invalid completion check: '+remaining)\n"
        code += "  if time.monotonic()>deadline:raise RuntimeError('clear-history operation did not finish')\n"
        code += "  time.sleep(.1)\n"
        code += " record['completion_check']='database cleared before capture stop'\n"
    code += " record['action_end_monotonic']=time.monotonic()\n"
    code += " pid_text=shell('pidof '+plan['bundle']).strip()\n"
    code += " assert pid_text and all(x.isdigit() for x in pid_text.split()),'app is not alive'\n"
    code += " record['pids']=list(map(int,pid_text.split()))\n"
    code += " record['stop_output']=shell('hiperf record --control stop')\n"
    code += " subprocess.run(['hdc','file','recv',device_file,str(root/'perf.data')],check=True,capture_output=True)\n"
    code += " assert (root/'perf.data').stat().st_size>0,'empty capture'\n"
    code += f" report_file='/data/local/tmp/profile-{token}.json'\n"
    code += " record['report_output']=shell('hiperf report --json -i '+device_file+' --pids '+','.join(pid_text.split())+' -o '+report_file)\n"
    code += " subprocess.run(['hdc','file','recv',report_file,str(root/'report.json')],check=True,capture_output=True)\n"
    code += " json.loads((root/'report.json').read_text())\n"
    code += " record['status']='CAPTURED'\n"
    code += "except Exception as exc:\n record['error']=str(exc)\n if prepared_ok:shell('hiperf record --control stop')\n"
    code += "(root/'capture.json').write_text(json.dumps(record,indent=2))\n"
    remote.python(code,timeout=600)
    remote.download(remote_base+'/capture.json',output/'capture.json')
    receipt=json.loads((output/'capture.json').read_text())
    receipt.update({'case':cid,'variant':variant,'round':round_number,'plan_sha256':plan_hash,
                    'signed_sha256':sign['audit']['sha256'],'remote_artifacts':remote_base,
                    'performance_verified':False})
    if fixture_hash:
        receipt['fixture_sha256']=fixture_hash
    (output/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if receipt['status']=='CAPTURED':
        if poem_import_fixture:
            receipt['poem_import_fixture_before']=import_before
            receipt['poem_import_fixture_after']=finish_import(remote,import_before)
        if poem_sync_fixture:
            receipt['poem_sync_fixture_before']=sync_before
            receipt['poem_sync_fixture_after']=finish_sync(remote,sync_before)
        if reader_fixture:
            receipt['reader_fixture_before']=reader_before
            receipt['reader_fixture_after']=finish_reader(remote,case,reader_before)
        if music_service:
            after=prepare_music_service(remote,case)
            same_instance(service_fixture,after)
            receipt['service_fixture_before']=service_fixture
            receipt['service_fixture_after']=after
        remote.download(remote_base+'/report.json',output/'report.json')
        # The device's JSON reporter includes all processes even with --pids.
        # Attribution must therefore be explicit; never use its system total.
        report=json.loads((output/'report.json').read_text())
        events=[e for e in report.get('recordSampleInfo',[]) if e.get('eventConfigName')=='hw-instructions']
        if len(events)!=1:raise RuntimeError('retired-instruction event is missing/ambiguous')
        processes=[p for p in events[0]['processes'] if p['pid'] in receipt['pids']]
        if len(processes)!=len(receipt['pids']):raise RuntimeError('app process missing from capture')
        receipt['app_instruction_period_sum']=sum(p['eventCount'] for p in processes)
        receipt['app_samples']=sum(t['sampleCount'] for p in processes for t in p['threads'])
        if receipt['app_instruction_period_sum']<=0 or receipt['app_samples']<=0:
            raise RuntimeError('app has no attributable instruction samples')
        (output/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(f'{cid}/{variant}/round-{round_number}: {receipt["status"]} {receipt.get("error", "")}',flush=True)
    if receipt['status']!='CAPTURED':
        raise RuntimeError('capture failed: '+receipt.get('error','unknown error'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    parser.add_argument('--variant',choices=['unfixed','fixed'],required=True)
    parser.add_argument('--round',type=int,default=1)
    fixtures=parser.add_mutually_exclusive_group()
    fixtures.add_argument('--browser-fixture',type=Path)
    fixtures.add_argument('--local-song-fixture',type=Path)
    fixtures.add_argument('--poem-fixture',type=Path)
    fixtures.add_argument('--bundled-audio',action='store_true')
    fixtures.add_argument('--music-service',action='store_true')
    fixtures.add_argument('--bundled-fonts',action='store_true')
    fixtures.add_argument('--reader-fixture',type=Path)
    fixtures.add_argument('--poem-import-fixture',type=Path)
    fixtures.add_argument('--poem-sync-fixture',type=Path)
    parser.add_argument('--remote',default='cityuPC')
    args=parser.parse_args()
    remote=Remote(args.remote)
    remote.upload(ROOT/'tools/ui_driver.py','/home/research/ohm-clean/tools/ui_driver.py')
    case=json.loads((ROOT/'cases'/args.case/'case.json').read_text())
    capture(remote,case,args.variant,args.round,args.browser_fixture,args.local_song_fixture,args.poem_fixture,args.bundled_audio,args.music_service,args.bundled_fonts,args.reader_fixture,args.poem_import_fixture,args.poem_sync_fixture)


if __name__=='__main__':
    main()
