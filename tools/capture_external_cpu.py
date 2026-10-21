#!/usr/bin/env python3
"""Collect generic system PMU samples across an external UI workload.

No probes or synchronization code are placed in the app. This emits raw capture
evidence only; it does not declare that a case meets its performance oracle.
"""
import argparse
import hashlib
import json
import uuid
import time
import shutil
from pathlib import Path
from measurement_paths import capture_root

from install_sqlite_fixture import install as install_fixture
from remote_device import Remote
from seed_local_songs import deploy as deploy_songs
from bundled_audio_fixture import for_case as packaged_audio
from music_service_fixture import prepare as prepare_music_service, same_instance
from bundled_font_fixture import for_case as packaged_fonts
from reader_data_fixture import prepare as prepare_reader, finish as finish_reader
from jingmo_import_fixture import prepare as prepare_import, finish as finish_import
from jingmo_sync_fixture import prepare as prepare_sync, finish as finish_sync
from reader_list_progress import CASE as READER_LIST_CASE
from reader_unread_badges import CASE as UNREAD_CASE
from playback_progress import CASES as PLAYBACK_CASES
from install_ytmusic_history_fixture import install as install_listening_history
from ytmusic_history_progress import verify_layout as verify_history_layout, verify_state as verify_history_state, read_state as read_history_state
from browser_visit_progress import CASE as BROWSER_VISIT_CASE
from interview_response_progress import CASE as INTERVIEW_RESPONSE_CASE
from interview_empty_history_fixture import CASE as HISTORY_SYNC_CASE, prepare as prepare_empty_history
from wan_web_progress import CASE as WAN_WEB_CASE
from install_wanharmony_history_fixture import install as prepare_wan_history
from wan_html_inputs import CASE as WAN_HTML_CASE

ROOT = Path(__file__).resolve().parents[1]


def capture(remote, case, variant, round_number, fixture=None, local_song_fixture=None, poem_fixture=None, bundled_audio=False, music_service=False, bundled_fonts=False, reader_fixture=None, poem_import_fixture=None, poem_sync_fixture=None, listening_history_fixture=None, preferences_path=None):
    cid = case['id']
    if sum(p is not None for p in (fixture,local_song_fixture,poem_fixture,reader_fixture,poem_import_fixture,poem_sync_fixture,listening_history_fixture))+int(bundled_audio)+int(music_service)+int(bundled_fonts)>1:
        raise ValueError('only one fixture may be supplied')
    if cid==HISTORY_SYNC_CASE and (any(p is not None for p in (fixture,local_song_fixture,poem_fixture,reader_fixture,poem_import_fixture,poem_sync_fixture,listening_history_fixture)) or bundled_audio or music_service or bundled_fonts):
        raise ValueError('search-flush trials require their own fresh empty native history fixture')
    if cid==WAN_WEB_CASE and (any(p is not None for p in (fixture,local_song_fixture,poem_fixture,reader_fixture,poem_import_fixture,poem_sync_fixture,listening_history_fixture)) or bundled_audio or music_service or bundled_fonts):
        raise ValueError('Web refresh trials require their own ordinary one-page native history fixture')
    if cid==WAN_HTML_CASE and (any(p is not None for p in (fixture,local_song_fixture,poem_fixture,reader_fixture,poem_import_fixture,poem_sync_fixture,listening_history_fixture)) or bundled_audio or music_service or bundled_fonts):
        raise ValueError('HTML trials require normal online first-page input, not injected data')
    if cid==INTERVIEW_RESPONSE_CASE:
        if any(p is not None for p in (fixture,local_song_fixture,poem_fixture,reader_fixture,poem_import_fixture,poem_sync_fixture,listening_history_fixture)) or bundled_audio or music_service or bundled_fonts:
            raise ValueError('response-log trials require normal online requests, not injected data')
        for name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):
            if remote.hdc(['shell','pidof '+name]).strip():
                raise RuntimeError('another profiler is live; do not alter its application')
        if remote.hdc(['shell','cat /sys/kernel/tracing/tracing_on']).strip()!='0':
            raise RuntimeError('another trace is active')
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
    output = capture_root(folder,case,'hiperf_instructions')/f'round-{round_number}'
    if case.get('measurement_revision') and output.exists():
        raise FileExistsError('preserve the revised CPU trial before any retry')
    if cid==INTERVIEW_RESPONSE_CASE and output.exists():
        raise FileExistsError('preserve the original response-log CPU trial before any retry')
    if cid==HISTORY_SYNC_CASE and output.exists():
        raise FileExistsError('preserve the original search-flush CPU trial before any retry')
    if cid==WAN_WEB_CASE and output.exists():
        raise FileExistsError('preserve the original Web refresh CPU trial before any retry')
    if cid==WAN_HTML_CASE and output.exists():
        raise FileExistsError('preserve the original HTML CPU trial before any retry')
    output.mkdir(parents=True,exist_ok=True)
    relative = output.relative_to(folder).as_posix()
    remote_base = f'/home/research/ohm-clean/{cid}/{variant}/{relative}'
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
    if listening_history_fixture:
        history_before=install_listening_history(remote,case,listening_history_fixture,preferences_path or '')
        fixture_hash=history_before['sha256']
    if cid==HISTORY_SYNC_CASE:
        empty_history_before=prepare_empty_history(remote,case,variant)
        fixture_hash=empty_history_before['sha256']
        for module in ('ui_driver.py','interview_history_progress.py','system_pss.py'):
            remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
    if cid==WAN_WEB_CASE:
        from wan_history_progress import PREFERENCES
        web_preparation=prepare_wan_history(remote,case,ROOT/'artifacts/fixtures/wan-web-weekly-page',PREFERENCES)
        fixture_hash=web_preparation['sha256']
        for module in ('ui_driver.py','wan_web_progress.py','native_hilog.py','system_pss.py','wan_history_progress.py','seed_wanharmony_history.py'):
            remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
    if cid==WAN_HTML_CASE:
        for module in ('ui_driver.py','wan_html_inputs.py','native_hilog.py','system_pss.py'):
            remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
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
    code += f"root=Path({remote_base!r}).resolve();plan_file=Path({remote_plan!r})\n"
    code += f"assert hashlib.sha256(plan_file.read_bytes()).hexdigest()=={plan_hash!r}\n"
    code += f"assert hashlib.sha256(Path({sign['signed_hap']!r}).read_bytes()).hexdigest()=={sign['audit']['sha256']!r}\n"
    code += "plan=json.loads(plan_file.read_text());ui=UI(shell,plan['bundle'],plan['ability'])\n"
    if poem_import_fixture or poem_sync_fixture:
        for module in ('jingmo_import_fixture.py','jingmo_data_service.py','rss_service_fixture.py','rss_data_service.py','rss_dataset.py','workstation_process.py','rss_workstation_lease.py','install_sqlite_fixture.py','remote_device.py'):
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
    if cid == INTERVIEW_RESPONSE_CASE:
        for module in ('interview_backend_inputs.py','native_hilog_stream.py','interview_response_progress.py','system_pss.py'):
            remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
        logger_binary=ROOT/'artifacts/native-hilog-stream/native-hilog-stream-v2'
        remote.upload(logger_binary,remote_base+'/native-logger')
        logger_device='/data/local/tmp/interview-logger-'+uuid.uuid4().hex
        code += "from interview_backend_inputs import enter_question_list,snapshot,encoded_snapshot,collect_rendered_stems\nfrom native_hilog_stream import NativeHiLogStream\n"
        code += "enter_question_list(ui,plan)\ninputs={'before':snapshot()}\ninputs['encoded']=encoded_snapshot(root/'encoded-backend.bin',inputs['before'])\n"
        code += f"logger_device={logger_device!r}\nsubprocess.run(['hdc','file','send',str(root/'native-logger'),logger_device],check=True,capture_output=True)\nshell('chmod 700 '+logger_device)\n"
        code += "logger_pid=shell('pidof '+plan['bundle']).strip();assert logger_pid.isdigit()\nlog_stream=NativeHiLogStream(shell,int(logger_pid),logger_device,root/'native-stream',180)\n"
    else:
        code += "ui.run([{'op':'stop'},{'op':'launch'}]);ui.run(plan['setup'])\n"
    if cid==WAN_HTML_CASE:
        code += "from wan_html_inputs import prepare_online as prepare_html_online,read_state as read_html_state\n"
        code += f"html_observation,html_preparation=prepare_html_online(ui,root,{variant!r})\n"
    if cid==WAN_WEB_CASE:
        code += "from wan_web_progress import read_state as read_web_state,verify as verify_web\nweb_before=read_web_state(shell,root/'native-logs','before')\n"
    if cid == INTERVIEW_RESPONSE_CASE:
        for module in ('interview_response_progress.py','system_pss.py'):
            remote.upload(ROOT/'tools'/module,'/home/research/ohm-clean/tools/'+module)
        code += "from interview_response_progress import read_state as read_responses,complete as complete_responses\n"
    if cid==HISTORY_SYNC_CASE:
        code += "from interview_history_progress import read_state as read_search_history,verify_observation as verify_search_history,keywords\n"
        code += "search_history_before=read_search_history(shell);assert keywords(search_history_before['raw_preferences'])==[]\n"
        code += "assert plan['measured'][0]['values']==['question'+str(i) for i in range(20)]\n"
    if fixture and cid == BROWSER_VISIT_CASE:
        remote.upload(ROOT/'tools/browser_visit_progress.py','/home/research/ohm-clean/tools/browser_visit_progress.py')
        code += "from browser_visit_progress import read_state as read_visits,complete_visits\nvisits_before=read_visits(shell)\n"
    if poem_sync_fixture:
        remote.upload(ROOT/'tools/jingmo_sync_progress.py','/home/research/ohm-clean/tools/jingmo_sync_progress.py')
        code += "from jingmo_sync_progress import read_state as read_sync_logs,complete_sync\nsync_logs_before=read_sync_logs(shell)\n"
    if reader_fixture and cid != READER_LIST_CASE:
        remote.upload(ROOT/'tools/rss_refresh_progress.py','/home/research/ohm-clean/tools/rss_refresh_progress.py')
        code += "from rss_refresh_progress import read_state,complete_refresh\nreader_before=read_state(shell)\n"
    if reader_fixture and cid == READER_LIST_CASE:
        remote.upload(ROOT/'tools/reader_list_progress.py','/home/research/ohm-clean/tools/reader_list_progress.py')
        code += "from reader_list_progress import observe,complete_render\nreader_launch_before=observe(ui)\n"
    if reader_fixture and cid == UNREAD_CASE:
        remote.upload(ROOT/'tools/reader_unread_badges.py','/home/research/ohm-clean/tools/reader_unread_badges.py')
        code += "from reader_unread_badges import complete_badges\n"
    if cid in PLAYBACK_CASES:
        remote.upload(ROOT/'tools/playback_progress.py','/home/research/ohm-clean/tools/playback_progress.py')
        code += "from playback_progress import check_progress\n"
        code += "playback_start_layout=ui.layout();playback_start_time=time.monotonic()\n"
    token=uuid.uuid4().hex
    code += f"device_file='/data/local/tmp/profile-{token}.data'\n"
    code += "assert not shell('pidof hiperf').strip(),'another profiler session is active'\n"
    code += "record={'status':'FAIL','event':'hw-instructions'}\n"
    if poem_sync_fixture:
        code += "record['poem_sync_logs_before']=sync_logs_before\n"
    code += "prepared_ok=False\n"
    code += "try:\n"
    if cid == INTERVIEW_RESPONSE_CASE:
        code += " log_stream.__enter__();responses_before=read_responses(shell)\n"
    code += " prepared=shell('hiperf record --control prepare -a --exclude-hiperf --cpu-limit 100 -f 1000 -e hw-instructions --call-stack dwarf --clockid boottime --kernel-callchain -m 1024 -o '+device_file)\n"
    code += " record['prepare_output']=prepared\n"
    code += " if 'fail' in prepared.lower() or 'error' in prepared.lower():raise RuntimeError(prepared)\n"
    code += " prepared_ok=True\n"
    code += " record['start_output']=shell('hiperf record --control start')\n"
    code += " if 'fail' in record['start_output'].lower() or 'error' in record['start_output'].lower():raise RuntimeError(record['start_output'])\n"
    code += " record['action_start_monotonic']=time.monotonic()\n"
    code += " ui.run(plan['measured']);ui.run(plan['verify'])\n"
    if cid==WAN_HTML_CASE:
        code += " html_actions_end=time.monotonic();html_after=read_html_state(ui,root/'native-logs','after')\n"
        code += " html_after.update(status='ORIGINAL_TWELVE_SWIPES_COMPLETED',action_start_monotonic=record['action_start_monotonic'],action_end_monotonic=html_actions_end)\n"
        code += " record['wan_html']=dict(html_observation,after=html_after);record['wan_html_preparation']=html_preparation\n"
    if cid==WAN_WEB_CASE:
        code += " web_actions_end=time.monotonic();web_after=read_web_state(shell,root/'native-logs','after')\n"
        code += " record['wan_web']={'pid':web_before['pid'],'stat_before':web_before['raw_stat'],'stat_after':web_after['raw_stat'],'before':web_before,'after':web_after,'actions_start_monotonic':record['action_start_monotonic'],'actions_end_monotonic':web_actions_end}\n"
        code += " record['wan_web']['progress']=verify_web(record['wan_web'])\n"
    if cid == INTERVIEW_RESPONSE_CASE:
        code += " record['interview_responses']=complete_responses(ui,responses_before)\n"
    if cid==HISTORY_SYNC_CASE:
        code += " search_history_after=read_search_history(shell);values=plan['measured'][0]['values']\n"
        code += " record['interview_history']={'before':search_history_before,'after':search_history_after,'values':values,'progress':verify_search_history(search_history_before,search_history_after,values)}\n"
    if fixture and cid == BROWSER_VISIT_CASE:
        code += " record['browser_visits']=complete_visits(ui,visits_before)\n"
    if poem_import_fixture:
        code += " record['poem_import_state']=complete_import(ui)\n"
    if poem_sync_fixture:
        code += " record['poem_sync_progress']=complete_sync(ui,sync_logs_before)\n"
        code += " record['poem_sync_state']=read_state(shell);verify_state(record['poem_sync_state'],True)\n"
    if reader_fixture and cid != READER_LIST_CASE:
        code += " record['reader_refresh']=complete_refresh(ui,reader_before)\n"
    if reader_fixture and cid == READER_LIST_CASE:
        code += " record['reader_list_render']=complete_render(ui,reader_launch_before)\n"
    if reader_fixture and cid == UNREAD_CASE:
        code += " record['reader_unread_badges']=complete_badges(ui)\n"
    if cid=='sepweather_font_register_per_page':
        code += " record['page_observations']=page_observations\n"
        code += " record['page_reconstructions']=verify_reconstructions(page_observations,plan['bundle'])\n"
    if cid in PLAYBACK_CASES:
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
    if listening_history_fixture:
        code += " history_started=time.monotonic();history_layout=ui.layout();history_ended=time.monotonic()\n"
        code += " record['listening_history_rows']={'layout':history_layout,'started_monotonic':history_started,'ended_monotonic':history_ended}\n"
    code += " record['action_end_monotonic']=time.monotonic()\n"
    code += " pid_text=shell('pidof '+plan['bundle']).strip()\n"
    code += " assert pid_text and all(x.isdigit() for x in pid_text.split()),'app is not alive'\n"
    code += " record['pids']=list(map(int,pid_text.split()))\n"
    code += " record['stop_output']=shell('hiperf record --control stop')\n"
    if cid == INTERVIEW_RESPONSE_CASE:
        code += " log_stream.close();inputs['native_stream']=log_stream.receipt()\n"
        code += " inputs['after']=snapshot();inputs['render']=collect_rendered_stems(ui,inputs['before']);inputs['render_stat']=shell('cat /proc/'+logger_pid+'/stat');record['interview_inputs']=inputs\n"
    code += " subprocess.run(['hdc','file','recv',device_file,str(root/'perf.data')],check=True,capture_output=True)\n"
    code += " assert (root/'perf.data').stat().st_size>0,'empty capture'\n"
    code += f" report_file='/data/local/tmp/profile-{token}.json'\n"
    code += " record['report_output']=shell('hiperf report --json -i '+device_file+' --pids '+','.join(pid_text.split())+' -o '+report_file)\n"
    code += " subprocess.run(['hdc','file','recv',report_file,str(root/'report.json')],check=True,capture_output=True)\n"
    code += " json.loads((root/'report.json').read_text())\n"
    code += " record['status']='CAPTURED'\n"
    code += "except Exception as exc:\n record['error']=str(exc)\n if prepared_ok:shell('hiperf record --control stop')\n"
    code += " if getattr(exc,'observation',None) is not None:record['failure_observation']=exc.observation\n"
    if cid == INTERVIEW_RESPONSE_CASE:
        code += "finally:\n log_stream.close()\n shell('rm -f '+logger_device)\n"
    code += "(root/'capture.json').write_text(json.dumps(record,indent=2))\n"
    # Long normal UI plans also need time to finalize/transfer/report native
    # samples. This is a transport budget, not added work or measured idle time.
    remote.python(code,timeout=max(600,int(case['collection']['step_duration_s'])+300))
    remote.download(remote_base+'/capture.json',output/'capture.json')
    receipt=json.loads((output/'capture.json').read_text())
    receipt.update({'case':cid,'variant':variant,'round':round_number,'plan_sha256':plan_hash,
                    'signed_sha256':sign['audit']['sha256'],'remote_artifacts':remote_base,
                    'performance_verified':False})
    if fixture_hash:
        receipt['fixture_sha256']=fixture_hash
    if cid==HISTORY_SYNC_CASE:
        receipt['empty_history_preparation']=empty_history_before
    if cid==WAN_WEB_CASE:
        receipt['wan_web_preparation']=web_preparation
    if cid==WAN_HTML_CASE and receipt.get('wan_html_preparation'):
        receipt['fixture_sha256']=receipt['wan_html_preparation']['sha256']
    if listening_history_fixture:
        receipt['listening_history_fixture_before']=history_before
    (output/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if receipt['status']=='CAPTURED':
        if cid == INTERVIEW_RESPONSE_CASE:
            from interview_backend_inputs import verify_capture_inputs
            for stream in ('stdout','stderr'):
                remote.download(remote_base+'/native-stream/'+stream+'.bin',output/'native-stream'/(stream+'.bin'))
            remote.download(remote_base+'/encoded-backend.bin',output/'encoded-backend.bin')
            receipt['interview_input_proof']=verify_capture_inputs(receipt,output)
            (output/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
            if round_number==1:
                retired=ROOT/'artifacts/retired-clean'/cid/variant/('pre-native-input-workload-'+str(time.time_ns()))
                retired.mkdir(parents=True,exist_ok=False)
                for name in ('workload.json','workload-device.json'):
                    if (folder/name).exists():shutil.copy2(folder/name,retired/name)
                (folder/'workload-device.json').write_text(json.dumps({'status':'PASS','interview_responses':receipt['interview_responses'],'interview_input_proof':receipt['interview_input_proof'],'source':'same original CPU trial; no UI rerun'},indent=2)+'\n')
                (folder/'workload.json').write_text(json.dumps({'case':cid,'variant':variant,'status':'PASS','plan_sha256':plan_hash,'signed_sha256':sign['audit']['sha256'],'interview_responses':receipt['interview_responses']['progress'],'interview_input_proof':receipt['interview_input_proof'],'performance_verified':False,'source':'normal HTTP and rendered-input checks in original first CPU trial'},indent=2)+'\n')
        if cid==WAN_HTML_CASE:
            from wan_html_inputs import verify_trial as verify_html_trial, verify_capture as verify_html_capture
            for label in ('setup','after'):
                for stream in ('stdout','stderr'):
                    name=label+'.'+stream+'.bin'
                    remote.download(remote_base+'/native-logs/'+name,output/'native-logs'/name)
            remote.download(remote_base+'/backend-first-page.json',output/'backend-first-page.json')
            observation=receipt['wan_html']
            observation['progress']=verify_html_trial(observation['setup'],observation['after'],observation['backend'],variant)
            verify_html_capture(observation,receipt['wan_html_preparation'],receipt['action_start_monotonic'],receipt['action_end_monotonic'],receipt['pids'],output)
            (output/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
            if round_number==1:
                retired=ROOT/'artifacts/retired-clean'/cid/variant/('pre-native-html-workload-'+str(time.time_ns()))
                retired.mkdir(parents=True,exist_ok=False)
                for name in ('workload.json','workload-device.json'):
                    if (folder/name).exists():shutil.copy2(folder/name,retired/name)
                preparation=dict(receipt['wan_html_preparation'],functional_read_verified=True)
                (folder/'workload-device.json').write_text(json.dumps({'status':'PASS','wan_html':observation,'source':'same original CPU trial; no UI rerun'},indent=2)+'\n')
                (folder/'workload.json').write_text(json.dumps({'case':cid,'variant':variant,'status':'PASS','plan_sha256':plan_hash,'signed_sha256':sign['audit']['sha256'],'fixture':preparation,'wan_html':observation['progress'],'performance_verified':False,'source':'normal online input/rendering checks in original first CPU trial'},indent=2)+'\n')
        if cid==WAN_WEB_CASE:
            from wan_web_progress import verify_capture as verify_web_capture, verify_fixture as verify_web_fixture
            for label in ('before','after'):
                for stream in ('stdout','stderr'):
                    name=label+'.'+stream+'.bin'
                    remote.download(remote_base+'/native-logs/'+name,output/'native-logs'/name)
            verify_web_capture(receipt['wan_web'],receipt['action_start_monotonic'],receipt['action_end_monotonic'],receipt['pids'],output)
            verify_web_fixture(web_preparation,receipt['wan_web'])
            if round_number==1:
                retired=ROOT/'artifacts/retired-clean'/cid/variant/('pre-native-web-workload-'+str(time.time_ns()))
                retired.mkdir(parents=True,exist_ok=False)
                for name in ('workload.json','workload-device.json'):
                    if (folder/name).exists():shutil.copy2(folder/name,retired/name)
                preparation=dict(web_preparation,functional_read_verified=True)
                (folder/'workload-device.json').write_text(json.dumps({'status':'PASS','wan_web':receipt['wan_web'],'source':'same original CPU trial; no UI rerun'},indent=2)+'\n')
                (folder/'workload.json').write_text(json.dumps({'case':cid,'variant':variant,'status':'PASS','plan_sha256':plan_hash,'signed_sha256':sign['audit']['sha256'],'fixture':preparation,'wan_web':receipt['wan_web']['progress'],'performance_verified':False,'source':'functional native callback checks in original first CPU trial'},indent=2)+'\n')
        if cid==HISTORY_SYNC_CASE:
            from interview_history_progress import verify_capture as verify_search_capture
            verify_search_capture(receipt['interview_history'],receipt['action_start_monotonic'],receipt['action_end_monotonic'],receipt['pids'])
            if round_number==1:
                retired=ROOT/'artifacts/retired-clean'/cid/variant/('pre-native-query-workload-'+str(time.time_ns()))
                retired.mkdir(parents=True,exist_ok=False)
                for name in ('workload.json','workload-device.json'):
                    if (folder/name).exists():shutil.copy2(folder/name,retired/name)
                preparation=dict(empty_history_before,functional_read_verified=True)
                (folder/'workload-device.json').write_text(json.dumps({'status':'PASS','interview_history':receipt['interview_history'],'source':'same original CPU trial; no UI rerun'},indent=2)+'\n')
                (folder/'workload.json').write_text(json.dumps({'case':cid,'variant':variant,'status':'PASS','plan_sha256':plan_hash,'signed_sha256':sign['audit']['sha256'],'fixture':preparation,'interview_history':receipt['interview_history']['progress'],'performance_verified':False,'source':'functional checks in original first CPU trial'},indent=2)+'\n')
        if listening_history_fixture:
            songs=json.loads((listening_history_fixture/'songs.json').read_text())
            receipt['listening_history_state_after']=read_history_state(remote,preferences_path)
            (output/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
            verify_history_state(receipt['listening_history_state_after']['raw_xml'],songs)
            receipt['listening_history_rows']['rows']=verify_history_layout(receipt['listening_history_rows']['layout'],songs)
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
    fixtures.add_argument('--listening-history-fixture',type=Path)
    parser.add_argument('--preferences-path',help='actual initialized native history preference path')
    parser.add_argument('--remote',default='cityuPC')
    args=parser.parse_args()
    remote=Remote(args.remote)
    remote.upload(ROOT/'tools/ui_driver.py','/home/research/ohm-clean/tools/ui_driver.py')
    case=json.loads((ROOT/'cases'/args.case/'case.json').read_text())
    capture(remote,case,args.variant,args.round,args.browser_fixture,args.local_song_fixture,args.poem_fixture,args.bundled_audio,args.music_service,args.bundled_fonts,args.reader_fixture,args.poem_import_fixture,args.poem_sync_fixture,args.listening_history_fixture,args.preferences_path)


if __name__=='__main__':
    main()
