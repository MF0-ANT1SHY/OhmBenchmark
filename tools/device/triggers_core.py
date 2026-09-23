#!/usr/bin/env python3
"""Per-case trigger automations + campaign runner.

Each trigger function signature: fn(ctx, rep) -> dict of collected artifacts.
ctx exposes: ohb module, case meta, capture(categories, seconds, in_thread),
hilog markers, artifact paths under results/<case_id>/
"""
import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ohb  # noqa: E402

RESULTS = os.path.join(REPO, 'results')


class Ctx:
    def __init__(self, case_id):
        self.case_id = case_id
        self.case = json.load(open(os.path.join(REPO, 'cases', case_id, 'case.json')))
        self.host_dir = os.path.join(REPO, self.case['host_app']['local_path'])
        self.outdir = os.path.join(RESULTS, case_id)
        os.makedirs(self.outdir, exist_ok=True)
        self.ability = ohb.ability_of(self.host_dir)
        self.trace_n = 0

    # --- capture helpers -------------------------------------------------
    def capture_during(self, categories, seconds, action, name='trace'):
        """Run `action()` while hitrace captures for `seconds` in background."""
        remote = f'/data/local/tmp/{self.case_id}_{name}_{self.trace_n}.chtrace'
        self.trace_n += 1
        t0 = time.time()
        p = subprocess.Popen([ohb.HDC, 'shell', f'hitrace -t {seconds} {" ".join(categories)} -o {remote}'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)
        marker_log = os.path.join(self.outdir, f'{name}_{self.trace_n}.hilog')
        hilog_proc = subprocess.Popen([ohb.HDC, 'shell', f'hilog > /data/local/tmp/{self.case_id}_{name}.hlog'],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = action()
        elapsed = time.time() - t0
        remain = seconds - elapsed + 1
        if remain > 0:
            time.sleep(remain)
        hilog_proc.terminate()
        ohb.hdc('file', 'recv', f'/data/local/tmp/{self.case_id}_{name}.hlog', marker_log)
        local = os.path.join(self.outdir, os.path.basename(remote))
        ohb.hdc('file', 'recv', remote, local)
        return {'trace': local, 'hilog': marker_log, 'result': result, 'capture_seconds': seconds}

    def launch_and_wait_home(self, marker=None, timeout=15, settle=3.0):
        ohb.force_stop()
        time.sleep(1.2)
        ohb.launch(self.ability)
        ohb.wait_pid(20)
        time.sleep(settle)

    def texts(self):
        return [ (n.get('attributes', {}).get('text') or '').strip()
                 for n in ohb.find_nodes(ohb.dump_layout())
                 if (n.get('attributes', {}).get('text') or '').strip() ]

    def tap_if(self, contains=None, text=None, **kw):
        n = ohb.find_nodes(ohb.dump_layout(), contains=contains, text=text, **kw)
        if n:
            ohb.tap_node(n[0])
            return True
        return False


# --------------------------------------------------------------------------
# browser family
# --------------------------------------------------------------------------

def browser_seed(ctx, pages=30):
    """Seed browsing history by submitting distinct searches (each leaves rows)."""
    ohb.launch(ctx.ability)
    time.sleep(3)
    for i in range(1, pages):
        n = ohb.find_nodes(ohb.dump_layout(), contains='搜索或输入网址')
        if not n:
            ohb.key('Back'); time.sleep(1.2)
            n = ohb.find_nodes(ohb.dump_layout(), contains='搜索或输入网址')
        if not n:
            ohb.launch(ctx.ability); time.sleep(3)
            n = ohb.find_nodes(ohb.dump_layout(), contains='搜索或输入网址')
        if not n:
            raise RuntimeError('cannot find browser search field')
        ohb.tap_node(n[0]); time.sleep(1.2)
        ohb.input_text_at(636, 1441, f'ohmbench seed {int(time.time()) % 100000} {i}')
        time.sleep(0.4)
        key = ohb.find_nodes(ohb.dump_layout(), text='搜索', type_='Text')
        ohb.tap_node(key[-1]) if key else ohb.key(2054)
        time.sleep(2.5)


def browser_open_history(ctx):
    """From browser home open the 浏览记录 dialog (middle bottom button)."""
    n = ohb.find_nodes(ohb.dump_layout(), contains='搜索或输入网址')
    if not n:  # a web page is open; cold-relaunch
        ohb.force_stop(); time.sleep(1); ohb.launch(ctx.ability); time.sleep(3.5)
    ohb.tap(630, 2615)
    time.sleep(1.5)


def t_browser_eager_history_load(ctx, rep):
    return ctx.capture_during(['ace', 'app', 'sched', 'disk', 'idle'], 15,
                              lambda: ctx.launch_and_wait_home(), name=f'rep{rep}')


def t_browser_history_delete_no_transaction(ctx, rep):
    def act():
        ctx.launch_and_wait_home()
        browser_open_history(ctx)
        time.sleep(1)
        # open settings dialog (4th bottom button) and clear history
        ohb.tap(882, 2615); time.sleep(1.5)
        ctx.tap_if(contains='清除')
        time.sleep(4)  # wait for delete to finish
    return ctx.capture_during(['app', 'sched', 'disk', 'idle'], 20, act, name=f'rep{rep}')


def t_browser_history_list_foreach(ctx, rep):
    def act():
        ctx.launch_and_wait_home()
        browser_open_history(ctx)
        time.sleep(1.5)
        for _ in range(6):
            ohb.swipe(630, 2200, 630, 800, 1200)
            time.sleep(1.2)
    return ctx.capture_during(['ace', 'app', 'sched'], 25, act, name=f'rep{rep}')


def t_browser_insert_date_lookup_cache(ctx, rep):
    def act():
        ctx.launch_and_wait_home()
        for i in range(20):
            n = ohb.find_nodes(ohb.dump_layout(), contains='搜索或输入网址')
            if not n:
                ohb.key('Back'); time.sleep(1); continue
            ohb.tap_node(n[0]); time.sleep(1)
            ohb.input_text_at(636, 1441, f'ohmbench b{rep} {i}')
            time.sleep(0.3)
            key = ohb.find_nodes(ohb.dump_layout(), text='搜索', type_='Text')
            ohb.tap_node(key[-1]) if key else ohb.key(2054)
            time.sleep(2)
    return ctx.capture_during(['ace', 'app', 'disk'], 90, act, name=f'rep{rep}')


TRIGGERS = {
    'browser_eager_history_load': t_browser_eager_history_load,
    'browser_history_delete_no_transaction': t_browser_history_delete_no_transaction,
    'browser_history_list_foreach': t_browser_history_list_foreach,
    'browser_insert_date_lookup_cache': t_browser_insert_date_lookup_cache,
}

SEEDS = {
    'browser_eager_history_load': lambda ctx: browser_seed(ctx, pages=25),
    'browser_history_delete_no_transaction': lambda ctx: browser_seed(ctx, pages=60),
    'browser_history_list_foreach': lambda ctx: browser_seed(ctx, pages=60),
    'browser_insert_date_lookup_cache': None,  # browsing IS the trigger
}


def default_trigger(ctx, rep):
    """Generic scenario: cold start + settle; covers startup-class cases."""
    return ctx.capture_during(['ace', 'app', 'sched', 'idle'], 15,
                              lambda: ctx.launch_and_wait_home(), name=f'rep{rep}')

# --------------------------------------------------------------------------
# wanharmony family (needs wanandroid.com reachable from device)
# --------------------------------------------------------------------------

WAN_BUNDLE = 'com.example.myapplication2'


def wan_open_article(ctx):
    """Tap the first tappable article card on home (title text row)."""
    root = ohb.dump_layout()
    for n in ohb.find_nodes(root, contains='作者：'):
        a = n.get('attributes', {})
        if a.get('type') in ('Text', 'Column', 'Row', 'Flex'):
            ohb.tap_node(n)
            return True
    return False


def wan_seed_history(ctx, opens=40):
    ctx.launch_and_wait_home(settle=6)
    for i in range(opens):
        if not wan_open_article(ctx):
            ohb.swipe(630, 2000, 630, 1600, 800)  # scroll a bit to reveal items
            time.sleep(1)
            continue
        time.sleep(2.5)  # let title event fire
        ohb.key('Back'); time.sleep(1.2)
        if i % 8 == 7:
            ohb.swipe(630, 2000, 630, 1500, 900)
            time.sleep(1)


def t_wan_html_decode_per_render(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        for _ in range(10):
            ohb.swipe(630, 2300, 630, 700, 1500)
            time.sleep(2)
    return ctx.capture_during(['ace', 'app', 'sched'], 45, act, name=f'rep{rep}')


def t_wan_persisted_home_list_growth(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        for _ in range(14):  # onReachEnd auto-load-more, 2s gate
            ohb.swipe(630, 2400, 630, 500, 1200)
            time.sleep(2.2)
    return ctx.capture_during(['app', 'sched', 'disk', 'idle'], 60, act, name=f'rep{rep}')


def t_wan_web_progress_log_storm(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        for i in range(5):
            if not wan_open_article(ctx):
                break
            time.sleep(4)  # page load + progress events
            ohb.key('Back'); time.sleep(1.5)
            ohb.swipe(630, 2200, 630, 1700, 900)  # next article
            time.sleep(1)
    return ctx.capture_during(['ace', 'app', 'sched'], 50, act, name=f'rep{rep}')


def t_wan_history_log_materialization(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        for i in range(10):
            if not wan_open_article(ctx):
                ohb.swipe(630, 2000, 630, 1600, 800); time.sleep(1); continue
            time.sleep(2.5)
            ohb.key('Back'); time.sleep(1.2)
    return ctx.capture_during(['ace', 'app', 'sched'], 60, act, name=f'rep{rep}')


# --------------------------------------------------------------------------
# cloudmusic family (needs a reachable NeteaseCloudMusicApi server)
# --------------------------------------------------------------------------

def cloud_open_toplist(ctx):
    """Explore tab -> 排行榜 -> first toplist card."""
    ctx.launch_and_wait_home(settle=6)
    if not ctx.tap_if(text='排行榜'):
        ctx.tap_if(contains='更多排行')
    time.sleep(2.5)
    ok = ctx.tap_if(text='飙升榜') or ctx.tap_if(text='新歌榜') or ctx.tap_if(text='热歌榜')
    time.sleep(3)
    return ok


def cloud_scroll_songs(ctx, seconds=25):
    t0 = time.time()
    while time.time() - t0 < seconds:
        ohb.swipe(630, 2300, 630, 700, 1400)
        time.sleep(1.4)


def t_cloud_indexof_in_render(ctx, rep):
    def act():
        if not cloud_open_toplist(ctx):
            raise RuntimeError('cannot open toplist (API server unreachable?)')
        cloud_scroll_songs(ctx)
    return ctx.capture_during(['ace', 'app', 'sched'], 45, act, name=f'rep{rep}')


def t_cloud_songcard_artists_concat(ctx, rep):
    return t_cloud_indexof_in_render(ctx, rep)


def t_cloud_search_result_foreach(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        n = ohb.find_nodes(ohb.dump_layout(), contains='Search something')
        if not n:
            raise RuntimeError('search box not found (API server unreachable?)')
        ohb.tap_node(n[0]); time.sleep(1.5)
        ohb.input_text_at(630, 1441, '周杰伦')
        time.sleep(0.5)
        key = ohb.find_nodes(ohb.dump_layout(), text='搜索', type_='Text')
        ohb.tap_node(key[-1]) if key else ohb.key(2054)
        time.sleep(4)
        for _ in range(5):
            if not ctx.tap_if(text='加载更多'):
                ohb.swipe(630, 2300, 630, 700, 1200)
                time.sleep(1.5)
        for _ in range(4):
            ohb.swipe(630, 2300, 630, 900, 1200); time.sleep(1)
            ohb.swipe(630, 900, 630, 2300, 1200); time.sleep(1)
    return ctx.capture_during(['ace', 'app', 'sched'], 50, act, name=f'rep{rep}')


def t_cloud_play_time_high_frequency_update(ctx, rep):
    def act():
        if not cloud_open_toplist(ctx):
            raise RuntimeError('cannot open toplist (API server unreachable?)')
        if not ctx.tap_if(text='播放全部'):
            raise RuntimeError('播放全部 not found')
        time.sleep(5)
        # open full player via bottom mini-player bar (song name row at bottom)
        root = ohb.dump_layout()
        cand = [n for n in ohb.find_nodes(root, type_='Row') if ohb._center(n) and ohb._center(n)[1] > 2450]
        if cand:
            ohb.tap_node(cand[-1])
        time.sleep(2)
    # 60s untouched playback
    return ctx.capture_during(['ace', 'app', 'sched', 'graphic'], 60, act, name=f'rep{rep}')


def t_cloud_local_song_memory_filter(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        if not ctx.tap_if(text='Me'):
            raise RuntimeError('Me tab not found')
        time.sleep(1.5)
        if not ctx.tap_if(text='Local Songs'):
            raise RuntimeError('Local Songs entry not found')
        time.sleep(2)
        n = ohb.find_nodes(ohb.dump_layout(), contains='Search something')
        if not n:
            raise RuntimeError('local songs search box not found')
        for i in range(5):
            ohb.tap_node(n[0]); time.sleep(1)
            ohb.input_text_at(630, 1441, 'a')
            time.sleep(0.4)
            key = ohb.find_nodes(ohb.dump_layout(), text='搜索', type_='Text')
            ohb.tap_node(key[-1]) if key else ohb.key(2054)
            time.sleep(2.5)
    return ctx.capture_during(['app', 'sched', 'disk', 'idle'], 40, act, name=f'rep{rep}')


TRIGGERS.update({
    'wanharmony_history_log_materialization': t_wan_history_log_materialization,
    'wanharmony_html_decode_per_render': t_wan_html_decode_per_render,
    'wanharmony_persisted_home_list_growth': t_wan_persisted_home_list_growth,
    'wanharmony_web_progress_log_storm': t_wan_web_progress_log_storm,
    'cloudmusic_indexof_in_render': t_cloud_indexof_in_render,
    'cloudmusic_songcard_artists_concat': t_cloud_songcard_artists_concat,
    'cloudmusic_search_result_foreach': t_cloud_search_result_foreach,
    'cloudmusic_play_time_high_frequency_update': t_cloud_play_time_high_frequency_update,
    'cloudmusic_local_song_memory_filter': t_cloud_local_song_memory_filter,
})

SEEDS.update({
    'wanharmony_history_log_materialization': lambda ctx: wan_seed_history(ctx, opens=40),
})
