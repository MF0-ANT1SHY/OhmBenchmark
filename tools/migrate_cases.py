#!/usr/bin/env python3
"""Rewrite every cases/<id>/case.json to the uniform v2 schema.

Keeps identity/provenance/commit fields; replaces trigger_steps + trace_config
with testcase (HapRay test case), collection (shared cases/collection.yaml spec),
test_oracle (CPU/memory metric the HapRay collection yields), and reproduction.
The original mechanism-level oracle is preserved as mechanism_oracle.

Usage: python3 tools/migrate_cases.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from build_testcases import SPECS  # noqa: E402

METRIC_DEF = {
    'hiperf_instructions':
        'raw-instruction-retired sample count attributed to the app process during the '
        'measured step, aggregated from perf.data (HapRay perf.db instruction counts).',
    'trace_cpu_ms':
        'on-CPU time of the app process during the measured step, from the sched events '
        'in trace.htrace.',
    'app_pss_bytes':
        'Pss of the app process after the workload, from the periodic smaps_rollup '
        'snapshots in memory/.',
    'nativehook_retained_bytes':
        'bytes still allocated at step end (malloc/free matching) from the nativehook '
        'plugin stream in trace.htrace.',
}

# case_id -> (oracle metric, evidence)
# evidence: (status, metric_measured, unfixed_values, fixed_values, note)
ORACLE = {
    'browser_eager_history_load': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [4862521465, 4717430103, 5046213668], [1511572583, 1345359423, 1530821367],
         'startup window: 4.86G vs 1.51G instructions (3.2x); cpu 2122 vs 747 ms')),
    'browser_history_delete_no_transaction': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [347565564, 343343678, 360078374], [4628830, 4260818, 5785336],
         '348M vs 4.6M instructions (75x); cpu 2735 vs 28 ms')),
    'browser_history_list_foreach': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [9637608919, 9630561356, 9725313176], [2789693645, 2751031972, 2799537880],
         '9.64G vs 2.79G instructions (3.5x); cpu 5986 vs 4041 ms; builds 200 vs 59')),
    'browser_insert_date_lookup_cache': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [980370663, 930619863, 988330253], [427037015, 425730609, 428455155],
         '980M vs 427M instructions (2.3x); cpu 5949 vs 2495 ms; 3000 vs 1002 statements')),
    'cloudmusic_indexof_in_render': ('hiperf_instructions',
        ('supporting', 'indexOf scan comparisons',
         [250500, 250500, 250500], [0, 0, 0],
         '250500 vs 0 comparisons per render pass (docs/analysis/measurement-indexof-scan.md)')),
    'cloudmusic_local_song_memory_filter': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions',
         [96834558, 91354916, 154449077], [30644715, 26854860, 102776450],
         '96.8M vs 30.6M instructions (3.2x) even at the small 10-song fixture; '
         'the gap grows with library size')),
    'cloudmusic_play_time_high_frequency_update': ('hiperf_instructions',
        ('supporting', 'state writes/minute',
         [600, 600, 600], [60, 60, 60],
         '600 vs 60 PLAY_TIME writes/minute (docs/analysis/measurement-play-time.md)')),
    'cloudmusic_search_result_foreach': ('hiperf_instructions',
        ('supporting', 'SongCard builds',
         [150, 150, 150], [12, 12, 12],
         '150 vs 12 row builds (docs/analysis/measurement-search-foreach.md)')),
    'cloudmusic_songcard_artists_concat': ('hiperf_instructions',
        ('supporting', 'concat allocations per row',
         [8, 8, 8], [0, 0, 0],
         '8 vs 0 string-concat allocations per row (docs/analysis/measurement-artists-concat.md)')),
    'interviewapp_response_log_full_stringify': ('hiperf_instructions',
        ('expected', 'response handler instructions',
         [], [], 'blocked on device by fixture reachability; the bench feeds a canned '
         'large payload through the same logging path in-app')),
    'interviewapp_search_history_sync_flush': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [3288553707, 3090556140, 3384493157], [165929778, 165402478, 171054649],
         '3.29G vs 166M instructions (20x); cpu 6867 vs 328 ms; 1000 vs 1 flushes')),
    'interviewapp_search_history_unbounded': ('app_pss_bytes',
        ('supporting', 'history entries retained',
         [500000, 500000, 500000], [2000, 2000, 2000],
         '500000 vs 2000 retained entries; 2.30G vs 2.47M instructions on the read path')),
    'jingmo_dataset_import_no_transaction': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [1726324143, 1701604706, 1751228897], [713365206, 712671122, 714310442],
         '1.73G vs 713M instructions (2.4x); cpu 4816 vs 239 ms')),
    'jingmo_random_poem_orderby_random': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [959038530, 926492371, 961287782], [7484806, 7461810, 7890165],
         '959M vs 7.5M instructions (128x); cpu 426 vs 40 ms')),
    'jingmo_sync_page_reimport': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [11506009207, 11444384089, 11694505915], [28662204, 23962817, 29937028],
         '11.5G vs 28.7M instructions (400x); cpu 1789 vs 123 ms')),
    'sepweather_font_register_per_page': ('hiperf_instructions',
        ('supporting', 'font registrations per MainPage creation',
         [2.0], [0.1],
         '2.0 vs 0.1 registrations (docs/analysis/measurement-font-register.md)')),
    'sheafreader_article_list_foreach': ('hiperf_instructions',
        ('expected', 'article card builds',
         [], [], 'unfixed container redesigned to Scroll+Column+ForEach so the eager-build '
         'mechanism actually manifests on this OS build (List+ForEach is already '
         'virtualised); control case browser_history_list_foreach separates 3.5x')),
    'sheafreader_extract_tag_tolowercase': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [25878521817, 25796251259, 25931635945], [11205986526, 11169483753, 11224455511],
         '25.9G vs 11.2G instructions (2.3x); cpu 3089 vs 1508 ms')),
    'sheafreader_insert_duplicate_exception': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions',
         [12837909544, 11594010171, 14676652174], [4922802397, 4907621328, 4944325933],
         '12.8G vs 4.92G instructions (2.6x) over the no-op refresh phase')),
    'sheafreader_refresh_feeds_sequential': ('trace_cpu_ms',
        ('measured', 'trace_cpu_ms',
         [5420, 5515, 5039], [3930, 4112, 3812],
         'cpu 5420 vs 3930 ms (+38%, disjoint ranges); total instructions match because '
         'the same fetches run, so the oracle is sched CPU time')),
    'sheafreader_unread_counts_n_plus_1': ('hiperf_instructions',
        ('measured', 'perf_hw-instructions / trace_cpu_ms',
         [2218196909, 2013965128, 2861558012], [87201809, 86596278, 87640704],
         '2.22G vs 87M instructions (25x); cpu 4102 vs 81 ms; 201 vs 2 queries')),
    'wanharmony_history_log_materialization': ('trace_cpu_ms',
        ('measured', 'trace_cpu_ms over the lifecycle-log phase',
         [49.9, 7.4, 8.3], [0.1, 0.1, 0.1],
         'phase-scoped cpu 49.9 vs 0.1 ms; whole-window instructions do not '
         'discriminate (page-open work dominates), so the oracle is the title-event '
         'phase CPU')),
    'wanharmony_html_decode_per_render': ('hiperf_instructions',
        ('supporting', 'htmlDecode calls per item',
         [3, 3, 3], [1, 1, 1],
         '3 vs 1 decode calls per rendered item (docs/analysis/measurement-html-decode.md)')),
    'wanharmony_persisted_home_list_growth': ('app_pss_bytes',
        ('supporting', 'persistent write bytes per load-more',
         [284970, 284970, 284970], [5111, 5111, 5111],
         '284970 vs 5111 bytes persisted per load-more; the in-memory list the '
         'persistence mirrors grows the same way (docs/analysis/measurement-persisted-growth.md)')),
    'wanharmony_web_progress_log_storm': ('hiperf_instructions',
        ('supporting', 'log calls per page load',
         [101, 101, 101], [5, 5, 5],
         '101 vs 5 hilog calls per page load (docs/analysis/measurement-progress-log.md)')),
    'weatherassistant_http_session_leak': ('nativehook_retained_bytes',
        ('expected', 'retained session/response objects',
         [], [], 'unfixed retains every created http session plus its full response in '
         'memory; fd counts were flat because sessions are pooled, so the oracle is '
         'retained bytes, not fds')),
    'weatherassistant_remote_weather_icons': ('hiperf_instructions',
        ('expected', 'icon fetch+decode instructions',
         [], [], 'icons come from a remote CDN on every cold start; fixed loads them '
         'from local resources, so fetch+decode instructions dominate the diff')),
    'ytmusic_current_playing_timeupdate': ('hiperf_instructions',
        ('supporting', 'page updates/minute',
         [600, 600, 600], [60, 60, 60],
         '600 vs 60 state updates/minute (docs/analysis/measurement-player-updates.md)')),
    'ytmusic_history_json_parse_per_row': ('hiperf_instructions',
        ('supporting', 'JSON.parse calls per render',
         [600, 600, 600], [200, 200, 200],
         '600 vs 200 parses per history-page render (docs/analysis/ytmusic-harness.md)')),
    'ytmusic_search_no_debounce': ('hiperf_instructions',
        ('expected', 'search requests per query',
         [], [], 'unfixed issues ~11 requests per typed query vs 1-2 fixed; each extra '
         'request costs serialise+send+parse+render instructions')),
}

MEMORY_CASES = {'interviewapp_search_history_unbounded',
                'wanharmony_persisted_home_list_growth',
                'weatherassistant_http_session_leak'}


def main():
    specs = {s[0]: s for s in SPECS}
    for cdir in sorted((ROOT / 'cases').iterdir()):
        if not cdir.is_dir():
            continue
        old = json.loads((cdir / 'case.json').read_text(encoding='utf-8'))
        cid = old['id']
        spec = specs[cid]
        name = f"{spec[1]}_{cid.split('_')[0]}_{spec[2]}"
        bundle = old['host_app']['bundle_name']
        module, ability = ('entry', 'EntryAbility')
        if cid.startswith('interviewapp'):
            module, ability = 'phone', 'PhoneAbility'
        elif cid.startswith('weatherassistant'):
            module, ability = 'alatus', 'AlatusAbility'
        elif cid.startswith('jingmo'):
            module = 'default'
        metric, ev = ORACLE[cid]
        status, measured_as, unf, fix, note = ev
        oracle = {
            'metric': metric,
            'definition': METRIC_DEF[metric],
            'comparison': 'unfixed >= 1.2 * fixed over >= 3 rounds per variant',
            'evidence': {
                'status': status,
                'measured_as': measured_as,
                'unfixed': unf,
                'fixed': fix,
                'note': note,
            },
            'mechanism_oracle': {
                'metric': old['test_oracle']['metric'],
                'definition': old['test_oracle']['definition'],
                'comparison': old['test_oracle']['comparison'],
            },
        }
        if 'auxiliary' in old['test_oracle']:
            oracle['mechanism_oracle']['auxiliary'] = old['test_oracle']['auxiliary']
        trigger = {'bench': 'bench', 'bench_ui': 'bench_ui', 'ui': 'ui',
                   'relaunch': 'relaunch', 'relaunch_noseed': 'relaunch'}[spec[3]]
        new = {
            'id': cid,
            'host_app': old['host_app'],
            'android_source_case': old['android_source_case'],
            'android_mechanism': old['android_mechanism'],
            'category': old['category'],
            'bug_description': old['bug_description'],
            'perf_scenarios': old['perf_scenarios'],
            'unfixed_commit': old['unfixed_commit'],
            'fixed_commit': old['fixed_commit'],
            'fix_summary': old['fix_summary'],
            'build': old['build'],
            'testcase': {
                'name': name,
                'py_file': f'testcase/{name}.py',
                'descriptor': f'testcase/{name}.json',
                'install_dir': f'perf_testing/hapray/testcases/{bundle}',
                'driver': 'DeviceTest',
                'module': module,
                'ability': ability,
                'trigger': trigger,
            },
            'collection': {
                'config': '../collection.yaml',
                'modes': ['htrace', 'hiperf'] + (['memory'] if cid in MEMORY_CASES else []),
                'step_duration_s': spec[5],
                'rounds': 3,
                'outputs': ['htrace/trace.htrace', 'hiperf/perf.data', 'pids.json',
                            'memory/', 'ui/', 'thermal/'],
            },
            'test_oracle': oracle,
            'reproduction': [
                f"git -C hosts/{Path(old['host_app']['local_path']).name} checkout case/{cid}/unfixed; "
                "apply the measurement harness patch for this case, build, sign and install the HAP.",
                f"cp cases/{cid}/testcase/{name}.* perf_testing/hapray/testcases/{bundle}/",
                f"python -m scripts.main perf --run_testcases {name} --round 3"
                + (' --memory' if cid in MEMORY_CASES else ''),
                f"git -C hosts/{Path(old['host_app']['local_path']).name} checkout case/{cid}/fixed; "
                "rebuild, reinstall and repeat identically.",
                "Compare test_oracle.metric across the two report sets: unfixed >= 1.2 * fixed.",
            ],
        }
        (cdir / 'case.json').write_text(
            json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(cid, '->', name, f'[{metric}:{status}]')


if __name__ == '__main__':
    main()
