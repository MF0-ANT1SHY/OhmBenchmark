#!/usr/bin/env python3
"""Accept paired clean CPU captures only after attribution/provenance checks."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path
from playback_progress import check_progress, CASES as PLAYBACK_CASES
from music_service_fixture import same_instance
from page_lifecycle import verify_reconstructions
from reader_data_fixture import CASES as READER_CASES, verify_preparation
from rss_refresh_progress import verify_observation
from jingmo_import_fixture import CASE as POEM_IMPORT_CASE, verify_state as verify_poem_state, verify_preparation as verify_poem_preparation, verify_capture_window as verify_poem_window
from jingmo_sync_fixture import CASE as POEM_SYNC_CASE, verify_preparation as verify_sync_preparation
from jingmo_sync_progress import verify_observation as verify_sync_progress, verify_capture as verify_sync_capture
from reader_list_progress import CASE as READER_LIST_CASE, verify_observation as verify_list_render, verify_capture as verify_list_capture
from reader_unread_badges import CASE as UNREAD_CASE, verify_layout as verify_unread_layout
from install_ytmusic_history_fixture import fixture_state as listening_fixture_state, CASE as LISTENING_HISTORY_CASE
from ytmusic_history_progress import verify_layout as verify_history_layout, verify_state as verify_history_state, verify_capture as verify_history_capture
from browser_visit_progress import CASE as BROWSER_VISIT_CASE, verify_observation as verify_browser_visits, verify_capture as verify_browser_visit_capture
from interview_response_progress import CASE as INTERVIEW_RESPONSE_CASE, verify_observation as verify_interview_responses, verify_capture as verify_interview_response_capture
from interview_empty_history_fixture import CASE as HISTORY_SYNC_CASE, verify as verify_empty_history
from interview_history_progress import verify_observation as verify_search_history, verify_capture as verify_search_capture

ROOT=Path(__file__).resolve().parents[1]


def accept(cid, write=True, require_pass=True, *, negative_screen=False):
    if negative_screen and (write or require_pass):
        raise ValueError('negative screening must be read-only and cannot accept performance')
    round_count = 1 if negative_screen else 3
    path=ROOT/'cases'/cid/'case.json'
    case=json.loads(path.read_text())
    if case['test_oracle']['metric']!='hiperf_instructions':
        raise ValueError('CPU capture cannot validate a different oracle')
    plan_hash=hashlib.sha256((path.parent/case['testcase']['workload']).read_bytes()).hexdigest()
    variants={}
    for variant in ['unfixed','fixed']:
        folder=ROOT/'artifacts/clean'/cid/variant
        sign=json.loads((folder/'sign.json').read_text())
        workload=json.loads((folder/'workload.json').read_text())
        if workload['status']!='PASS' or workload['plan_sha256']!=plan_hash or workload['signed_sha256']!=sign['audit']['sha256']:
            raise RuntimeError('matching real workload execution not proven')
        if cid == INTERVIEW_RESPONSE_CASE:
            device=json.loads((folder/'workload-device.json').read_text())
            if verify_interview_responses(device['interview_responses']) != workload.get('interview_responses'):
                raise RuntimeError('successful normal question-list requests are not proven')
        if cid==BROWSER_VISIT_CASE:
            device=json.loads((folder/'workload-device.json').read_text())
            if (not workload.get('fixture',{}).get('functional_read_verified')
                    or verify_browser_visits(device['browser_visits'])!=workload.get('browser_visits')):
                raise RuntimeError('fifteen complete ordinary saved navigations are not proven')
        if cid==HISTORY_SYNC_CASE:
            device=json.loads((folder/'workload-device.json').read_text());observation=device['interview_history']
            preparation=workload['fixture']
            if (not preparation.get('functional_read_verified') or preparation['variant']!=variant or
                    verify_empty_history(preparation)!=preparation['sha256'] or
                    verify_search_history(observation['before'],observation['after'],observation['values'])!=workload['interview_history']):
                raise RuntimeError('real twenty-query workload and empty input preparation are not proven')
        if cid==LISTENING_HISTORY_CASE:
            fixture=workload['fixture']
            fixture_folder=Path(fixture['fixture_dir'])
            history_fixture,_=listening_fixture_state(fixture_folder)
            songs=json.loads((fixture_folder/'songs.json').read_text())
            device=json.loads((folder/'workload-device.json').read_text())
            if (not fixture.get('installation_verified') or not fixture.get('functional_read_verified')
                    or fixture['sha256']!=history_fixture['fixture_sha256']
                    or verify_history_layout(device['phases']['verify']['layout'],songs)!=workload.get('history_rows')):
                raise RuntimeError('ordinary listening-history data and rendered song rows are not proven')
            verify_history_state(workload['history_state']['raw_xml'],songs)
        if cid==POEM_IMPORT_CASE:
            device=json.loads((folder/'workload-device.json').read_text())
            verify_poem_state(device['poem_import_state'],True)
            verify_poem_preparation(workload['fixture'],workload['fixture_after'])
        if cid==POEM_SYNC_CASE:
            device=json.loads((folder/'workload-device.json').read_text())
            verify_sync_progress(device['poem_sync_progress'])
            verify_poem_state(device['poem_sync_state'],True)
            verify_sync_preparation(workload['fixture'],workload['fixture_after'])
        if cid in READER_CASES:
            device=json.loads((folder/'workload-device.json').read_text())
            if cid == UNREAD_CASE:
                if verify_unread_layout(device['reader_unread_badges']['layout'])!=workload.get('reader_unread_badges'):
                    raise RuntimeError('correct ordinary feed unread counts are not proven')
            if cid == READER_LIST_CASE:
                if verify_list_render(device['reader_list_render'])!=workload.get('reader_list_render'):
                    raise RuntimeError('normal complete article rendering is not proven')
            elif verify_observation(device['reader_refresh'])!=workload.get('reader_refresh'):
                raise RuntimeError('normal complete reader refresh is not proven')
            verify_preparation(workload['fixture'],workload['fixture_after'])
        if cid=='sepweather_font_register_per_page':
            device=json.loads((folder/'workload-device.json').read_text())
            if verify_reconstructions(device['page_observations'],case['host_app']['bundle_name'])!=workload.get('page_reconstructions'):
                raise RuntimeError('page reconstruction receipt differs from raw lifecycle observations')
        if cid=='browser_history_delete_no_transaction' and (
                workload.get('functional_check')!='all history rows and dates cleared through the production UI'
                or workload.get('cleared_tables',0)<2):
            raise RuntimeError('complete history-row deletion through the UI is not proven')
        if cid in PLAYBACK_CASES:
            device=json.loads((folder/'workload-device.json').read_text())
            phases=device['phases']
            progress=check_progress(phases['setup']['layout'],phases['measured']['layout'],
                                    case['host_app']['bundle_name'],phases['measured']['elapsed_s'])
            if progress!=workload.get('playback_progress'):
                raise RuntimeError('real playback progression is not proven')
        samples=[]
        captures=[]
        fixture_hashes=set()
        for round_no in range(1,round_count+1):
            capture_dir=folder/'cpu-captures'/f'round-{round_no}'
            receipt=json.loads((capture_dir/'capture.json').read_text())
            if receipt['status']!='CAPTURED' or receipt['plan_sha256']!=plan_hash or receipt['signed_sha256']!=sign['audit']['sha256']:
                raise RuntimeError('capture provenance mismatch')
            if receipt.get('fixture_sha256') != workload.get('fixture',{}).get('sha256'):
                raise RuntimeError('capture fixture differs from the validated workload')
            if cid == INTERVIEW_RESPONSE_CASE:
                verify_interview_response_capture(receipt['interview_responses'],receipt['action_start_monotonic'],receipt['action_end_monotonic'],receipt['pids'])
            if cid==HISTORY_SYNC_CASE:
                preparation=receipt['empty_history_preparation']
                if preparation['variant']!=variant or verify_empty_history(preparation)!=receipt['fixture_sha256']:
                    raise RuntimeError('CPU trial did not reset the dedicated search-history store')
                verify_search_capture(receipt['interview_history'],receipt['action_start_monotonic'],receipt['action_end_monotonic'],receipt['pids'])
            if cid==BROWSER_VISIT_CASE:
                verify_browser_visit_capture(receipt['browser_visits'],receipt['action_start_monotonic'],receipt['action_end_monotonic'])
            if cid==LISTENING_HISTORY_CASE:
                preparation=receipt['listening_history_fixture_before']
                if (not preparation.get('installation_verified') or preparation['sha256']!=receipt['fixture_sha256']
                        or preparation['deployed_sha256']!=history_fixture['preferences_sha256']):
                    raise RuntimeError('listening-history capture input was not reset to the verified ordinary catalogue')
                verify_history_state(receipt['listening_history_state_after']['raw_xml'],songs)
                verify_history_capture(receipt['listening_history_rows'],songs,receipt['action_start_monotonic'],receipt['action_end_monotonic'])
            if cid==POEM_IMPORT_CASE:
                verify_poem_window(receipt['poem_import_state'],receipt['action_start_monotonic'],receipt['action_end_monotonic'])
                verify_poem_preparation(receipt['poem_import_fixture_before'],receipt['poem_import_fixture_after'])
                if receipt['poem_import_fixture_before']['sha256']!=receipt['fixture_sha256']:
                    raise RuntimeError('poetry capture data identity differs from validated cold import')
            if cid==POEM_SYNC_CASE:
                verify_sync_capture(receipt['poem_sync_progress'],receipt['action_start_monotonic'],receipt['action_end_monotonic'])
                verify_poem_window(receipt['poem_sync_state'],receipt['action_start_monotonic'],receipt['action_end_monotonic'])
                verify_sync_preparation(receipt['poem_sync_fixture_before'],receipt['poem_sync_fixture_after'])
                if receipt['poem_sync_fixture_before']['sha256']!=receipt['fixture_sha256']:
                    raise RuntimeError('cached poetry capture input differs from the validated data')
            if cid in READER_CASES:
                if cid == UNREAD_CASE:
                    badges=receipt['reader_unread_badges']
                    if verify_unread_layout(badges['layout'])!=badges['counts']:
                        raise RuntimeError('unread badge summary differs from native UI')
                    if not receipt['action_start_monotonic']<=badges['started_monotonic']<=badges['ended_monotonic']<=receipt['action_end_monotonic']:
                        raise RuntimeError('unread badges were not observed inside the measured window')
                verify_preparation(receipt['reader_fixture_before'],receipt['reader_fixture_after'])
                if receipt['reader_fixture_before']['sha256']!=receipt['fixture_sha256']:
                    raise RuntimeError('reader capture input differs from its verified native database')
                if cid == READER_LIST_CASE:
                    verify_list_capture(receipt['reader_list_render'],receipt['action_start_monotonic'],receipt['action_end_monotonic'],receipt['pids'])
                else:
                    verify_observation(receipt['reader_refresh'])
                    observation=receipt['reader_refresh']
                    if (observation['before']['ended_monotonic']>receipt['action_start_monotonic']
                            or observation['after']['started_monotonic']<receipt['action_start_monotonic']
                            or observation['after']['ended_monotonic']>receipt['action_end_monotonic']):
                        raise RuntimeError('reader completion was not observed within the measured window')
            if cid=='sepweather_font_register_per_page':
                if verify_reconstructions(receipt['page_observations'],case['host_app']['bundle_name'])!=receipt.get('page_reconstructions'):
                    raise RuntimeError('page reconstruction within capture is not proven')
            if cid in {'cloudmusic_songcard_artists_concat','cloudmusic_search_result_foreach','cloudmusic_indexof_in_render'}:
                if workload.get('functional_check')!='normal song titles and artist lines match the ordinary music catalogue':
                    raise RuntimeError('correct music catalogue rows in the UI are not proven')
                same_instance(workload['fixture'],workload['fixture_after'])
                same_instance(receipt['service_fixture_before'],receipt['service_fixture_after'])
                if receipt['service_fixture_before']['sha256']!=receipt['fixture_sha256']:
                    raise RuntimeError('music data identity differs from capture fixture')
            if cid=='browser_history_delete_no_transaction' and receipt.get('completion_check')!='database cleared before capture stop':
                raise RuntimeError('async database completion within the capture is not proven')
            if cid in PLAYBACK_CASES:
                observation=receipt['playback_observation']
                progress=check_progress(observation['start_layout'],observation['end_layout'],
                                        case['host_app']['bundle_name'],observation['elapsed_s'])
                if progress!=receipt.get('playback_progress'):
                    raise RuntimeError('playback progression receipt differs from raw snapshots')
            report_path=capture_dir/'report.json'
            report=json.loads(report_path.read_text())
            events=[e for e in report['recordSampleInfo'] if e['eventConfigName']=='hw-instructions']
            if len(events)!=1:raise RuntimeError('missing/ambiguous hardware instruction event')
            processes=[p for p in events[0]['processes'] if p['pid'] in receipt['pids']]
            if len(processes)!=len(receipt['pids']):raise RuntimeError('missing app process samples')
            for process in processes:
                if report['processNameMap'][str(process['pid'])]!=case['host_app']['bundle_name']:
                    raise RuntimeError('samples belong to a different process')
            value=sum(p['eventCount'] for p in processes)
            count=sum(t['sampleCount'] for p in processes for t in p['threads'])
            if value<=0 or count<=0 or value!=receipt['app_instruction_period_sum']:
                raise RuntimeError('invalid app instruction attribution')
            if receipt['action_end_monotonic']<=receipt['action_start_monotonic']:
                raise RuntimeError('invalid capture window')
            samples.append(value)
            fixture_hashes.add(receipt.get('fixture_sha256'))
            captures.append({'round':round_no,'report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
                             'app_samples':count,'remote_artifacts':receipt['remote_artifacts']})
        variants[variant]={'samples':samples,'captures':captures,'fixtures':fixture_hashes,
                           'signed_sha256':sign['audit']['sha256']}
    fixtures=variants['unfixed']['fixtures']|variants['fixed']['fixtures']
    if len(fixtures)!=1 or None in fixtures:raise RuntimeError('identical fixture is not proven across all rounds')
    ratios=[u/f for u,f in zip(variants['unfixed']['samples'],variants['fixed']['samples'])]
    median_ratio=statistics.median(variants['unfixed']['samples'])/statistics.median(variants['fixed']['samples'])
    passed=min(ratios)>=1.2 and median_ratio>=1.2
    if negative_screen and passed:
        raise ValueError('first pair is not negative; three complete pairs are required for acceptance')
    if passed and cid==HISTORY_SYNC_CASE:
        raise RuntimeError('primary criterion met; independent native flush-mechanism verification is still required')
    results={}
    for variant,data in variants.items():
        result={'status':'PASS' if passed else 'FAIL','metric':'hiperf_instructions','rounds':round_count,'samples':data['samples'],
                'median':statistics.median(data['samples']),'paired_ratios':ratios,'median_ratio':median_ratio,
                'plan_sha256':plan_hash,'signed_sha256':data['signed_sha256'],'fixture_sha256':next(iter(fixtures)),
                'method':'app-process sampled retired-instruction period sum from system hiperf; not system total',
                'captures':data['captures'],'legacy_evidence_reused':False}
        results[variant]=result
        if write:
            (ROOT/'artifacts/clean'/cid/variant/'performance.json').write_text(json.dumps(result,indent=2)+'\n')
    case['test_oracle']['evidence']={'status':'measured_clean' if passed else 'measured_clean_failed','metric':'hiperf_instructions',
        'unfixed':variants['unfixed']['samples'],'fixed':variants['fixed']['samples'],'median_ratio':median_ratio,
        'rounds_per_variant':round_count,'legacy_evidence_reused':False,'note':
        'Every paired round exceeds 1.2x; app process explicitly selected from the system report.' if passed else
        'Clean captures are valid, but the required 1.2x performance improvement is not met; this case is not accepted.'}
    case['test_oracle']['definition']='Sampled retired-instruction period sum (hw-instructions) attributed to the app process in the complete externally driven measured window.'
    if write:
        path.write_text(json.dumps(case,indent=2,ensure_ascii=False)+'\n')
        if passed:
            print(f'{cid}: clean CPU oracle verified, median ratio={median_ratio:.3f}x')
    if not passed and require_pass:
        raise RuntimeError(f'performance criterion not met: {ratios}')
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    args=parser.parse_args()
    accept(args.case)
