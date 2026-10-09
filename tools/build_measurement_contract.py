#!/usr/bin/env python3
"""Build the measurement contract registry from the case specs and the recorded runs.

For every case this records:
  - the metric its cases/<id>/case.json test_oracle declares
  - the measurement primitive needed to collect it (elapsed/cpu/count/external)
  - the probe field a harness should emit for it
  - any auxiliary counter that probes ALREADY emit for this case

It invents no data. `collected_metric` is only set when measurements/results.json
holds actual run rounds for the case.
"""
import json
import glob
import collections
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO.parent / 'OhmBenchmark-data'

PRIMITIVE = {
    'elapsed': {'obtainable_in_probe': True, 'note': 'wall time between the OHMB markers (already collected for every round)'},
    'cpu': {'obtainable_in_probe': False, 'note': 'scheduler CPU between markers; derived from the hitrace by tools/device/analyze.py'},
    'count': {'obtainable_in_probe': True, 'note': 'a counter the bench entry must expose; the probe protocol returns a bare number today'},
    'external': {'obtainable_in_probe': False, 'note': 'needs host-side collection (fd/socket/network byte counters)'},
}

# Cases whose probes already emit an auxiliary counter into summary.json, and the
# field name(s) used. Verified against measurements/summary.json.
AUX_COUNTERS = {
    'browser_history_list_foreach': ['history_components_created'],
    'sheafreader_article_list_foreach': ['article_components_created'],
    'weatherassistant_http_session_leak': ['fd_before', 'fd_after'],
}

# Cases where the declared mechanism was tested and does NOT manifest on this OS build,
# so no amount of extra measurement on these builds will separate the variants.
MECHANISM_ABSENT = {
    'sheafreader_article_list_foreach': (
        'the unfixed ForEach over List is already virtualised on this OS build: the fixture '
        'loads 600 articles but only 37 cards build in BOTH variants, while the control case '
        'browser_history_list_foreach (same ForEach->LazyForEach change, 1000 rows) separates '
        'cleanly at 200 vs 59'),
    'weatherassistant_http_session_leak': (
        'the leak does not reproduce at 120 requests: fd counts were flat in both variants'),
}

CONTRACT = {
    'sheafreader_article_list_foreach': ('cpu', 'article_components_created',
        'MECHANISM ABSENT, proven by control: the fixture loads 600 articles yet only 37 cards '
        'build in BOTH variants, because the unfixed ForEach over List is already virtualised on '
        'this OS build. browser_history_list_foreach changes the same construct and DOES '
        'discriminate (200 vs 59 builds, 1000 rows), so the fix is sound but this case cannot '
        'show it. Only trace CPU separates the variants (+11.79%, non-overlapping). elapsed_ms is '
        'constant by construction (fixed 10s window). Needs oracle re-declaration to trace_cpu_ms '
        'or a counter taken at the same stage the browser counter uses.'),
    'sheafreader_insert_duplicate_exception': ('cpu', 'no_op_refresh_cpu_ms',
        'a 22-36s elapsed window dominated by fixture work; must isolate the no-op refresh phase and read trace CPU'),
    'weatherassistant_http_session_leak': ('external', 'fd_before+fd_after',
        'fd counts ARE collected (fd_before/fd_after) and were flat in both variants, so the leak does not reproduce at 120 requests'),
    'cloudmusic_local_song_memory_filter': ('elapsed', 'search_result_latency_ms',
        'only ~10 method calls measured; fixture must reach >=300 songs and many searches to clear the noise floor'),
    'browser_eager_history_load': ('cpu', 'startup_cpu_time_ms',
        'declared startup CPU; reported trace_cpu_ms over a fixed 10s window'),
    'browser_history_delete_no_transaction': ('elapsed', 'clear_history_wall_time_ms', 'reported elapsed_ms - same quantity'),
    'browser_history_list_foreach': ('count', 'history_components_created',
        'declared component builds; the probe DID emit history_components_created (200 unfixed vs 59 fixed) but the exporter reported trace_cpu_ms instead'),
    'browser_insert_date_lookup_cache': ('count', 'rdb_statements_per_page_save',
        'declared RDB statement count; reported elapsed_ms. The count is observable in the probe'),
    'interviewapp_search_history_sync_flush': ('count', 'flush_count_per_search_burst',
        'declared flush count; reported trace_cpu_ms. The count is observable in the probe'),
    'interviewapp_search_history_unbounded': ('count', 'history_entries_and_render_cost',
        'declared entry count + render cost; reported elapsed_ms'),
    'jingmo_dataset_import_no_transaction': ('elapsed', 'dataset_import_wall_time_ms', 'reported elapsed_ms - same quantity'),
    'jingmo_random_poem_orderby_random': ('elapsed', 'random_read_query_ms', 'reported elapsed_ms - same quantity'),
    'jingmo_sync_page_reimport': ('elapsed', 'revisit_sync_page_cost', 'reported elapsed_ms - proxy for revisit cost'),
    'sheafreader_extract_tag_tolowercase': ('cpu', 'feed_parse_cpu_ms', 'declared parse CPU; reported elapsed_ms'),
    'sheafreader_refresh_feeds_sequential': ('elapsed', 'refresh_all_wall_time_ms', 'reported elapsed_ms - same quantity'),
    'sheafreader_unread_counts_n_plus_1': ('count', 'sidebar_count_queries_per_refresh',
        'declared query count (201->2 observed); reported elapsed_ms. The count is observable in the probe'),
    'wanharmony_history_log_materialization': ('cpu', 'title_event_cpu_ms',
        'declared title-event CPU; reported elapsed_ms over the lifecycle-log phase only'),
    'cloudmusic_indexof_in_render': ('elapsed', 'search_result_latency_ms', 'never measured: host trigger/install instability'),
    'cloudmusic_play_time_high_frequency_update': ('count', 'player_page_updates_per_minute',
        'never measured: host instability; state-update count is countable in the probe'),
    'cloudmusic_search_result_foreach': ('count', 'search_list_render_cpu_and_jank',
        'never measured: host instability; needs component count + trace CPU'),
    'cloudmusic_songcard_artists_concat': ('cpu', 'row_build_cpu_overhead', 'never measured: host instability'),
    'interviewapp_response_log_full_stringify': ('cpu', 'response_handler_cpu_ms',
        'blocked: local fixture response arrives as a string and is rejected before the logging path'),
    'sepweather_font_register_per_page': ('elapsed', 'mainpage_build_ms', 'never measured: launched cleanly 6x but no formal round (budget)'),
    'wanharmony_html_decode_per_render': ('cpu', 'scroll_cpu_ms_per_item', 'never measured: launched cleanly 9x but no formal round (budget)'),
    'wanharmony_persisted_home_list_growth': ('count', 'persistent_write_bytes_per_loadmore',
        'never measured (budget); declared bytes per load-more needs an I/O counter'),
    'wanharmony_web_progress_log_storm': ('count', 'log_calls_per_pageload', 'never measured (budget); log call count is countable'),
    'weatherassistant_remote_weather_icons': ('external', 'icon_first_paint_ms_and_net_bytes',
        'never measured: injected .cjs error; declared metric needs network byte accounting'),
    'ytmusic_current_playing_timeupdate': ('count', 'player_page_updates_per_minute',
        'never measured: host repo absent; rerender count is countable'),
    'ytmusic_history_json_parse_per_row': ('count', 'history_page_render_cpu_ms', 'never measured: host repo absent'),
    'ytmusic_search_no_debounce': ('count', 'search_requests_per_query',
        'never measured: host repo absent; request count is countable/loggable'),
}


def pattern_rounds(rounds: dict) -> list:
    """Flatten the per-variant rounds into a list tagged with its variant."""
    out = []
    for variant in ('unfixed', 'fixed'):
        for r in rounds.get(variant, []) or []:
            out.append(dict(r, variant=variant))
    return out


def metric_from_rounds(rs: list, declared: str):
    """The metric the recorded rounds carry, preferring the declared name.

    The hand-written table said several cases 'reported elapsed_ms' while their records also hold
    trace_cpu_ms and main_thread_cpu_ms, so their declared CPU metrics were in fact collected.
    """
    if not rs:
        return None
    fields = {k for r in rs for k in r}
    if declared in fields:
        return declared
    for candidate in ('trace_cpu_ms', 'main_thread_cpu_ms'):
        if candidate in fields:
            return candidate
    return 'elapsed_ms' if 'elapsed_ms' in fields else None


def ranges_separate(rounds: dict, metric: str) -> bool:
    """True when the unfixed and fixed ranges for `metric` are disjoint."""
    def vals(variant):
        return [r[metric] for r in (rounds.get(variant) or [])
                if isinstance(r.get(metric), (int, float))]
    u, f = vals('unfixed'), vals('fixed')
    if not u or not f:
        return False
    return max(f) < min(u) or max(u) < min(f)

def main():
    specs = {}
    for f in sorted(glob.glob(str(REPO / 'cases' / '*' / 'case.json'))):
        d = json.loads(Path(f).read_text(encoding='utf-8'))
        specs[d['id']] = d

    results = {}
    rp = DATA / 'measurements' / 'results.json'
    if rp.exists():
        results = {c['case']: c for c in json.loads(rp.read_text(encoding='utf-8'))['cases']}

    cases = {}
    for cid, spec in sorted(specs.items()):
        oracle = spec['test_oracle']['metric']
        prim, field, why = CONTRACT.get(cid, ('elapsed', '', 'unclassified'))
        r = results.get(cid, {})
        rounds = r.get('rounds') or {}
        n_rounds = len(rounds.get('unfixed', [])) + len(rounds.get('fixed', []))
        # the records decide: the hand-written table went stale and claimed cases
        # reported elapsed_ms while their rounds also carried trace_cpu_ms
        collected = metric_from_rounds(pattern_rounds(rounds), oracle) if n_rounds > 0 else None
        cases[cid] = {
            'host': spec['host_app']['name'],
            'oracle_metric': oracle,
            'collected_metric': collected,
            # A name match is not enough: the objective requires the declared metric to have been
            # collected AND its unfixed/fixed ranges to be disjoint before a case counts as a
            # clear difference.
            'oracle_satisfied': bool(collected) and collected == oracle
                                and ranges_separate(rounds, collected),
            'rounds_recorded': n_rounds,
            'primitive': prim,
            'probe_field': field,
            'aux_counters': AUX_COUNTERS.get(cid, []),
            'mechanism': 'absent' if cid in MECHANISM_ABSENT else 'present',
            'mechanism_note': MECHANISM_ABSENT.get(cid, ''),
            'measurement_status': r.get('status', '未完成测试'),
            'gap': why,
        }

    measured = {c: v for c, v in cases.items() if v['rounds_recorded'] > 0}
    doc = {
        '$comment': 'Measurement contract per case: what the case declares, what was collected with real '
                    'rounds, the primitive needed, and any auxiliary counter probes already emit. '
                    'Generated by tools/build_measurement_contract.py - do not hand-edit.',
        'case_count': len(cases),
        'measured_case_count': len(measured),
        'cases': cases,
        'primitives': PRIMITIVE,
    }
    out = REPO / 'cases' / 'measurement-contract.json'
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    print(f"wrote {out.relative_to(REPO)}")
    print(f"  cases                  : {doc['case_count']}")
    print(f"  cases with real rounds : {doc['measured_case_count']}")
    print(f"  primitives needed      : {dict(collections.Counter(c['primitive'] for c in cases.values()))}")
    print(f"  cases with aux counter : {[c for c,v in cases.items() if v['aux_counters']]}")


if __name__ == '__main__':
    main()


