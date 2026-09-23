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
        # 200MB buffer: the default 18MB ring holds only ~8s of sched volume,
        # which drops the app's early events on longer flows
        p = subprocess.Popen([ohb.HDC, 'shell',
                              f'hitrace -b 204800 -t {seconds} {" ".join(categories)} -o {remote}'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)
        marker_log = os.path.join(self.outdir, f'{name}_{self.trace_n}.hilog')
        # clear the buffer first: fresh window = minimal flow-control loss
        ohb.shell('hilog -r')
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

def browser_open_history(ctx):
    """Open the 浏览记录 dialog. Dialogs only open on the home page and a cold
    relaunch always lands there (no session restore), so force-stop first."""
    ohb.force_stop()
    time.sleep(1)
    ohb.launch(ctx.ability)
    ohb.wait_pid(20)
    time.sleep(3.5)
    ohb.tap(630, 2615)  # 3rd bottom button (PagesButton) at y=2615
    time.sleep(1.5)


def t_browser_eager_history_load(ctx, rep):
    return ctx.capture_during(['ace', 'app', 'sched', 'disk', 'idle'], 15,
                              lambda: ctx.launch_and_wait_home(), name=f'rep{rep}')


def browser_uitest_trigger(ctx, method, categories, seconds, tail_swipes=0, rep=1):
    """Run a Hypium flow inside the capture window, then optional swipes."""
    def act():
        out = ohb.run_uitest(f'ActsOhbBrowser#{method}', timeout=seconds)
        if 'Pass: 1' not in out:
            raise RuntimeError(f'{method} failed: '
                               + ' '.join(l for l in out.splitlines() if 'Error in' in l or 'stream=' in l)[:200])
        for _ in range(tail_swipes):
            ohb.swipe(630, 2200, 630, 800, 1200)
            time.sleep(1.2)
    return ctx.capture_during(categories, seconds, act, name=f'rep{rep}')


def t_browser_history_delete_no_transaction(ctx, rep):
    # NOTE: the UI 清除浏览记录 button never touches the DB (RdbUtils.deleteAll
    # is dead code in every host commit) — see results/proof.jsonl.
    return browser_uitest_trigger(ctx, 'clearHistory', ['app', 'sched', 'disk', 'idle'],
                                  30, rep=rep)


def t_browser_history_list_foreach(ctx, rep):
    return browser_uitest_trigger(ctx, 'openHistory', ['ace', 'app', 'sched'],
                                  30, tail_swipes=6, rep=rep)


def t_browser_insert_date_lookup_cache(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=4)
        for i in range(20):
            # URL bar is type Search on home and web pages alike
            n = ohb.find_nodes(ohb.dump_layout(), type_='Search')
            if not n:
                raise RuntimeError('search field not found')
            cx, cy = ohb._center(n[0])
            # local mock pages: near-instant load, so inter-save wall time is
            # dominated by the save path itself (oracle metric)
            ohb.shell(f'uitest uiInput inputText {cx} {cy} '
                      f'http://127.0.0.1:8978/page/q{rep}i{i}t{int(time.time()) % 100000}.com')
            time.sleep(0.6)
            ohb.key(2054)
            time.sleep(2.0)
    return ctx.capture_during(['ace', 'app', 'sched', 'disk'], 90, act, name=f'rep{rep}')


def _hilog_count(needle):
    out = ohb.shell(f'hilog -x | grep -c {needle}').strip()
    m = re.search(r'\d+', out)
    return int(m.group()) if m else 0


def browser_seed_multidate(ctx, batches=10):
    """Seed browsing history across N distinct days: set the device date per
    batch, browse 6 local mock pages (hdc rport 8978 -> mock_server /page/*),
    restore the real date. CLI inputText path (Hypium driver.inputText does not
    commit text on this device). Fixed pacing per item; hilog save counters are
    lossy (flow control), so the seed is verified once at the end via the
    cold-start eager load (查询到记录 row lines), not per item."""
    for b in range(batches):
        ohb.set_device_date(days_ago=batches - 1 - b)
        ohb.force_stop()
        time.sleep(1)
        ohb.launch(ctx.ability)
        ohb.wait_pid(20)
        time.sleep(4)
        for i in range(6):
            n = ohb.find_nodes(ohb.dump_layout(), type_='Search')
            if not n:
                ohb.restore_device_date()
                raise RuntimeError(f'seed: search field not found (batch {b} item {i})')
            cx, cy = ohb._center(n[0])
            ohb.shell(f'uitest uiInput inputText {cx} {cy} '
                      f'http://127.0.0.1:8978/page/b{b}s{i}t{int(time.time()) % 100000}.com')
            time.sleep(1.0)
            ohb.key(2054)
            time.sleep(3.0)  # page load + onPageEnd save
    ohb.restore_device_date()
    # verify: cold start materializes every row (eager path logs one line/row)
    ohb.force_stop()
    time.sleep(1)
    ohb.shell('hilog -r')
    ohb.launch(ctx.ability)
    ohb.wait_pid(20)
    time.sleep(8)
    rows = _hilog_count('查询到记录')
    if rows < batches * 6 * 0.5:
        raise RuntimeError(f'seed verify: only {rows} rows visible '
                           f'(expected ~{batches * 6}; 无痕浏览(private mode) on?)')
    return rows


TRIGGERS = {
    'browser_eager_history_load': t_browser_eager_history_load,
    'browser_history_delete_no_transaction': t_browser_history_delete_no_transaction,
    'browser_history_list_foreach': t_browser_history_list_foreach,
    'browser_insert_date_lookup_cache': t_browser_insert_date_lookup_cache,
}

SEEDS = {
    'browser_eager_history_load': lambda ctx: browser_seed_multidate(ctx, batches=10),
    'browser_history_delete_no_transaction': lambda ctx: browser_seed_multidate(ctx, batches=18),
    'browser_history_list_foreach': lambda ctx: browser_seed_multidate(ctx, batches=18),
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


def wan_article_rows(ctx):
    """Home article rows (title-ish Texts). Author lines use a half-width
    colon ('作者: '), so matching on '作者：' never fired; filter rows by
    content instead of searching for the author marker."""
    root = ohb.dump_layout()
    out = []
    for n in ohb.find_nodes(root, type_='Text'):
        a = n.get('attributes', {})
        t = (a.get('text') or '').strip()
        b = ohb._bounds(n)
        if not t or not b or len(t) < 12:
            continue
        cy = (b[1] + b[3]) // 2
        if cy > 2450 or cy < 400:  # status/toolbar + bottom nav
            continue
        if any(k in t for k in ('作者', '分享人', '置顶文章', '推荐文章')) or t.startswith('['):
            continue
        out.append(n)
    return out


def wan_open_article(ctx):
    """Tap the bottom-most article row in the viewport (fresh content lives
    deeper in the infinite feed; re-opening the top row adds no new history
    because historyList filters duplicate urls)."""
    rows = wan_article_rows(ctx)
    if not rows:
        return False
    rows.sort(key=lambda n: ohb._center(n)[1])
    ohb.tap_node(rows[-1])
    return True


def wan_seed_history(ctx, opens=100):
    """Open `opens` distinct articles so historyList grows to 100+ entries."""
    ctx.launch_and_wait_home(settle=6)
    misses = 0
    for i in range(opens):
        if not wan_open_article(ctx):
            misses += 1
            if misses > 12:
                raise RuntimeError('wan seed: no article rows found (feed dead?)')
            ohb.swipe(630, 2100, 630, 1500, 900)
            time.sleep(1.5)
            continue
        time.sleep(3.2)  # article load + onTitleReceive history write
        ohb.key('Back')
        time.sleep(1.4)
        ohb.swipe(630, 2200, 630, 1900, 900)  # reveal fresh rows below
        time.sleep(1.2)
    return opens


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
            time.sleep(3.5)
            ohb.key('Back'); time.sleep(1.4)
    return ctx.capture_during(['ace', 'app', 'sched'], 70, act, name=f'rep{rep}')


# --------------------------------------------------------------------------
# cloudmusic family (needs a reachable NeteaseCloudMusicApi server)
# --------------------------------------------------------------------------

def cloud_config_api(ctx):
    """First-launch config: point the app at the local NeteaseCloudMusicApi
    (device localhost:3000 via hdc rport) through the 设置在线服务 sheet."""
    ctx.launch_and_wait_home(settle=6)
    if ctx.tap_if(contains='设置在线服务'):
        time.sleep(2)
        field = ohb.find_nodes(ohb.dump_layout(), type_='TextInput') or \
            ohb.find_nodes(ohb.dump_layout(), type_='Search') or \
            ohb.find_nodes(ohb.dump_layout(), type_='TextArea')
        if field:
            ohb.tap_node(field[0]); time.sleep(1)
            ohb.input_text_at(*ohb._center(field[0]), 'http://127.0.0.1:3000')
            time.sleep(0.5)
            ohb.key(2054); time.sleep(1)
        if not ctx.tap_if(text='确定') and not ctx.tap_if(text='保存'):
            ohb.key('Back')
        time.sleep(2)
        ctx.launch_and_wait_home(settle=6)


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
        cloud_config_api(ctx)
        if not cloud_open_toplist(ctx):
            raise RuntimeError('cannot open toplist (API server unreachable?)')
        cloud_scroll_songs(ctx)
    return ctx.capture_during(['ace', 'app', 'sched'], 45, act, name=f'rep{rep}')


def t_cloud_songcard_artists_concat(ctx, rep):
    return t_cloud_indexof_in_render(ctx, rep)


def t_cloud_search_result_foreach(ctx, rep):
    def act():
        cloud_config_api(ctx)
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
        cloud_config_api(ctx)
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
        cloud_config_api(ctx)
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
    'wanharmony_history_log_materialization': lambda ctx: wan_seed_history(ctx, opens=100),
})

# --------------------------------------------------------------------------
# jingmo family (dataset CDN p1-cdn.jingmo.ruaruan.com is alive)
# --------------------------------------------------------------------------

def jingmo_open_sync(ctx):
    """Home -> gear icon (top-right, no text) -> 同步数据."""
    ctx.launch_and_wait_home(settle=4)
    root = ohb.dump_layout()
    # gear = Image in the header row (top ~128-260px, right side)
    gears = [n for n in ohb.find_nodes(root, type_='Image')
             if ohb._center(n) and ohb._center(n)[1] < 320 and ohb._center(n)[0] > 1000]
    if gears:
        ohb.tap_node(gears[0])
        time.sleep(1.5)
    if not ctx.tap_if(text='同步数据'):
        raise RuntimeError('同步数据 not found (gear icon missed?)')
    time.sleep(2)


def jingmo_seed_import(ctx):
    jingmo_open_sync(ctx)
    time.sleep(25)  # dataset fetch + import


def t_jingmo_dataset_import_no_transaction(ctx, rep):
    ohb.shell(f'bm clean -n {ohb.BUNDLE} -d')  # empty DB per repetition
    time.sleep(1)
    return ctx.capture_during(['app', 'sched', 'disk', 'idle'], 40, jingmo_open_sync, name=f'rep{rep}')


def t_jingmo_random_poem_orderby_random(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=4)
        if not ctx.tap_if(text='经典诗文'):
            raise RuntimeError('经典诗文 grid item not found')
        time.sleep(3)
        for _ in range(10):
            if not ctx.tap_if(text='刷新'):
                break
            time.sleep(1.2)
    return ctx.capture_during(['app', 'sched', 'disk'], 30, act, name=f'rep{rep}')


def t_jingmo_sync_page_reimport(ctx, rep):
    return ctx.capture_during(['app', 'sched', 'disk', 'idle'], 15, jingmo_open_sync, name=f'rep{rep}')


# --------------------------------------------------------------------------
# sepweather (offline-capable; weather API key empty but UI renders)
# --------------------------------------------------------------------------

def t_sepweather_font_register_per_page(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=5)
        for _ in range(10):
            if not ctx.tap_if(id_='AddAddressBtn'):
                raise RuntimeError('AddAddressBtn not found')
            time.sleep(1.5)
            ohb.key('Back')  # LocationListPage is a router page: Back pops safely
            time.sleep(1.5)
    return ctx.capture_during(['ace', 'app', 'sched', 'disk'], 40, act, name=f'rep{rep}')


# --------------------------------------------------------------------------
# weatherassistant (amap key invalid: forecast panel won't render, but city
# add/refresh requests still fire -> fd-leak case executable in degraded mode)
# --------------------------------------------------------------------------

def weather_add_cities(ctx, n=8):
    ctx.launch_and_wait_home(settle=5)
    for city in ['上海市', '北京市', '南京市', '武汉市', '成都市', '杭州市', '天津市', '重庆市'][:n]:
        if not ctx.tap_if(text='添加'):
            break
        time.sleep(1.5)
        if not ctx.tap_if(text=city):
            ohb.key('Back'); time.sleep(1); continue
        time.sleep(1)
        # per-row 添加 button
        rows = ohb.find_nodes(ohb.dump_layout(), text=city)
        if rows:
            b = ohb._bounds(rows[0])
            if b:
                ohb.tap(b[2] - 60, (b[1] + b[3]) // 2)
        time.sleep(1.5)
        ctx.tap_if(text='完成')
        time.sleep(2)


def t_weatherassistant_http_session_leak(ctx, rep):
    def act():
        weather_add_cities(ctx, n=6)
        time.sleep(3)
    return ctx.capture_during(['app', 'sched', 'network', 'net'], 50, act, name=f'rep{rep}')


def t_weatherassistant_remote_weather_icons(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        time.sleep(6)
        # switch 2 city tabs via horizontal swipe on the panel
        for _ in range(4):
            ohb.swipe(950, 1200, 300, 1200, 600); time.sleep(2.5)
            ohb.swipe(300, 1200, 950, 1200, 600); time.sleep(2.5)
    return ctx.capture_during(['app', 'sched', 'network', 'net', 'ace'], 40, act, name=f'rep{rep}')


# --------------------------------------------------------------------------
# interviewapp (live API; search needs one login with prefilled credentials)
# --------------------------------------------------------------------------

def interview_login_if_needed(ctx):
    """After tapping the home search bar: login page may appear (first run)."""
    time.sleep(2)
    if ctx.tap_if(contains='已阅读并同意'):
        time.sleep(0.5)
    if ctx.tap_if(text='立即登录'):
        time.sleep(4)


def interview_open_search(ctx):
    ctx.launch_and_wait_home(settle=6)
    if not ctx.tap_if(contains='搜索题目'):
        raise RuntimeError('home search bar not found')
    interview_login_if_needed(ctx)
    if not ctx.tap_if(contains='请输入关键词'):
        # maybe already on search page with a previous keyword
        n = ohb.find_nodes(ohb.dump_layout(), type_='Search')
        if not n:
            raise RuntimeError('search input not found after login')
    return True


def interview_submit_search(ctx, kw):
    n = ohb.find_nodes(ohb.dump_layout(), contains='请输入关键词') or \
        ohb.find_nodes(ohb.dump_layout(), type_='Search')
    c = ohb._center(n[0]) if n else (630, 300)
    ohb.input_text_at(*c, kw)
    time.sleep(0.4)
    ohb.key(2054)  # IME search/enter
    time.sleep(1.2)


def t_interviewapp_response_log_full_stringify(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        for _ in range(12):
            ohb.swipe(630, 2300, 630, 700, 1400)
            time.sleep(1.6)
    return ctx.capture_during(['app', 'sched'], 40, act, name=f'rep{rep}')


def t_interviewapp_search_history_sync_flush(ctx, rep):
    def act():
        interview_open_search(ctx)
        for i in range(10):
            interview_submit_search(ctx, f'ohmbench {rep} {i} {int(time.time())%10000}')
        time.sleep(5)  # allow trailing flush window
    return ctx.capture_during(['app', 'sched', 'disk', 'idle'], 45, act, name=f'rep{rep}')


def t_interviewapp_search_history_unbounded(ctx, rep):
    def act():
        interview_open_search(ctx)
        for i in range(20):
            interview_submit_search(ctx, f'kw{rep}{i}{int(time.time())%100000}')
        time.sleep(2)
    return ctx.capture_during(['app', 'sched', 'disk'], 50, act, name=f'rep{rep}')


# --------------------------------------------------------------------------
# ytmusic (search backend dead; requires URL patch -> local mock + rport)
# --------------------------------------------------------------------------

def ytmusic_play_first_home_song(ctx):
    ctx.launch_and_wait_home(settle=6)
    for t in ('再听一次',):
        ctx.tap_if(text=t)
    # tap a song row (any Text matching known song names)
    root = ohb.dump_layout()
    for n in ohb.find_nodes(root, contains='Welcome to the Black Parade'):
        ohb.tap_node(n)
        return True
    return False


def t_ytmusic_current_playing_timeupdate(ctx, rep):
    def act():
        if not ytmusic_play_first_home_song(ctx):
            raise RuntimeError('no home song row found')
        time.sleep(3)
    # 60s untouched playback on now-playing page
    return ctx.capture_during(['ace', 'app', 'sched', 'graphic'], 60, act, name=f'rep{rep}')


def ytmusic_seed_history(ctx, plays=27):
    """Play tracks to populate history (PersistentStorage, survives reinstall)."""
    ctx.launch_and_wait_home(settle=6)
    for i in range(plays):
        root = ohb.dump_layout()
        rows = [n for n in ohb.find_nodes(root, type_='Text')
                if ohb._center(n) and ohb._center(n)[1] < 2300 and len(n.get('attributes', {}).get('text') or '') > 3
                and n.get('attributes', {}).get('text') not in ('首页', '探索', '媒体库', '升级')]
        if not rows:
            break
        ohb.tap_node(rows[min(i, len(rows) - 1)])
        time.sleep(3)
        ohb.key('Back'); time.sleep(1.5)
        ohb.swipe(630, 2200, 630, 1500, 900)
        time.sleep(1)


def t_ytmusic_history_json_parse_per_row(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        if not ctx.tap_if(text='媒体库'):
            raise RuntimeError('媒体库 tab not found')
        time.sleep(2)
        # history icon: leftmost of 3 header icons (top-right, no text)
        root = ohb.dump_layout()
        icons = [n for n in ohb.find_nodes(root, type_='Button')
                 if ohb._center(n) and ohb._center(n)[1] < 400 and ohb._center(n)[0] > 700]
        if icons:
            ohb.tap_node(icons[0])
        time.sleep(2.5)
        for _ in range(5):
            ohb.swipe(630, 2200, 630, 800, 1300)
            time.sleep(1.4)
    return ctx.capture_during(['ace', 'app', 'sched'], 35, act, name=f'rep{rep}')


def t_ytmusic_search_no_debounce(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=6)
        root = ohb.dump_layout()
        icons = [n for n in ohb.find_nodes(root, type_='Button')
                 if ohb._center(n) and ohb._center(n)[1] < 400 and ohb._center(n)[0] > 1000]
        if not icons:
            raise RuntimeError('search icon not found on home header')
        ohb.tap_node(icons[0]); time.sleep(2)
        ohb.input_text_at(630, 300, 'ohmbench1')
        time.sleep(1)
        ohb.key(2054)
        time.sleep(3)
    return ctx.capture_during(['app', 'sched', 'network'], 30, act, name=f'rep{rep}')


# --------------------------------------------------------------------------
# sheafreader (needs feeds; add via dialog against mock feed server on :8978)
# --------------------------------------------------------------------------

def sheaf_add_feeds(ctx, n=10):
    ctx.launch_and_wait_home(settle=5)
    for i in range(n):
        if not ctx.tap_if(text='添加订阅源'):
            # sidebar may have closed; re-open via drawer edge swipe
            ohb.swipe(60, 1400, 700, 1400, 600)
            time.sleep(1.5)
            if not ctx.tap_if(text='添加订阅源'):
                raise RuntimeError('添加订阅源 not found')
        time.sleep(1.5)
        field = ohb.find_nodes(ohb.dump_layout(), contains='example.com/feed.xml')
        if not field:
            raise RuntimeError('feed URL field not found')
        ohb.tap_node(field[0]); time.sleep(0.8)
        ohb.input_text_at(630, 1000, f'http://127.0.0.1:8978/feed{i}.xml')
        time.sleep(0.5)
        ctx.tap_if(text='添加订阅源')  # dialog confirm button
        time.sleep(3)  # fetch+validate+insert


def sheaf_refresh_all(ctx):
    """Tap the refresh circle in the sidebar header (top-right of drawer)."""
    root = ohb.dump_layout()
    # refresh icon: rightmost small circle near sidebar header
    for n in ohb.find_nodes(root, type_='Button'):
        b = ohb._bounds(n)
        if b and b[1] < 700 and b[0] < 900 and (b[2] - b[0]) < 160:
            ohb.tap_node(n)
            return True
    return False


def t_sheafreader_article_list_foreach(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=5)
        if not ctx.tap_if(text='全部文章'):
            raise RuntimeError('全部文章 not found in sidebar')
        time.sleep(2)
        for _ in range(5):
            if not ctx.tap_if(text='加载更多'):
                ohb.swipe(700, 2300, 700, 900, 1300)
                time.sleep(1.5)
        for _ in range(6):
            ohb.swipe(700, 2300, 700, 800, 1400)
            time.sleep(1.3)
    return ctx.capture_during(['ace', 'app', 'sched'], 45, act, name=f'rep{rep}')


def _sheaf_refresh_case(ctx, rep, seconds):
    def act():
        ctx.launch_and_wait_home(settle=5)
        if not sheaf_refresh_all(ctx):
            raise RuntimeError('refresh icon not found')
        time.sleep(seconds)
    return ctx.capture_during(['app', 'sched', 'disk', 'idle'], seconds + 15, act, name=f'rep{rep}')


def t_sheafreader_extract_tag_tolowercase(ctx, rep):
    return _sheaf_refresh_case(ctx, rep, 25)


def t_sheafreader_insert_duplicate_exception(ctx, rep):
    return _sheaf_refresh_case(ctx, rep, 25)


def t_sheafreader_refresh_feeds_sequential(ctx, rep):
    return _sheaf_refresh_case(ctx, rep, 30)


def t_sheafreader_unread_counts_n_plus_1(ctx, rep):
    def act():
        ctx.launch_and_wait_home(settle=5)
        ctx.tap_if(text='全部文章')
        time.sleep(2)
        for _ in range(5):
            rows = [n for n in ohb.find_nodes(ohb.dump_layout(), type_='Text')
                    if ohb._center(n) and 400 < ohb._center(n)[1] < 2200
                    and len(n.get('attributes', {}).get('text') or '') > 8]
            if not rows:
                break
            ohb.tap_node(rows[0]); time.sleep(2.5)
            # close reader: top-left circle button in reader pane
            back = [n for n in ohb.find_nodes(ohb.dump_layout(), type_='Button')
                    if ohb._center(n) and ohb._center(n)[1] < 500 and ohb._center(n)[0] < 500]
            if back:
                ohb.tap_node(back[0])
            time.sleep(1.5)
    return ctx.capture_during(['app', 'sched', 'disk'], 40, act, name=f'rep{rep}')


TRIGGERS.update({
    'jingmo_dataset_import_no_transaction': t_jingmo_dataset_import_no_transaction,
    'jingmo_random_poem_orderby_random': t_jingmo_random_poem_orderby_random,
    'jingmo_sync_page_reimport': t_jingmo_sync_page_reimport,
    'sepweather_font_register_per_page': t_sepweather_font_register_per_page,
    'weatherassistant_http_session_leak': t_weatherassistant_http_session_leak,
    'weatherassistant_remote_weather_icons': t_weatherassistant_remote_weather_icons,
    'interviewapp_response_log_full_stringify': t_interviewapp_response_log_full_stringify,
    'interviewapp_search_history_sync_flush': t_interviewapp_search_history_sync_flush,
    'interviewapp_search_history_unbounded': t_interviewapp_search_history_unbounded,
    'ytmusic_current_playing_timeupdate': t_ytmusic_current_playing_timeupdate,
    'ytmusic_history_json_parse_per_row': t_ytmusic_history_json_parse_per_row,
    'ytmusic_search_no_debounce': t_ytmusic_search_no_debounce,
    'sheafreader_article_list_foreach': t_sheafreader_article_list_foreach,
    'sheafreader_extract_tag_tolowercase': t_sheafreader_extract_tag_tolowercase,
    'sheafreader_insert_duplicate_exception': t_sheafreader_insert_duplicate_exception,
    'sheafreader_refresh_feeds_sequential': t_sheafreader_refresh_feeds_sequential,
    'sheafreader_unread_counts_n_plus_1': t_sheafreader_unread_counts_n_plus_1,
})

SEEDS.update({
    'jingmo_random_poem_orderby_random': jingmo_seed_import,
    'jingmo_sync_page_reimport': jingmo_seed_import,
    'interviewapp_search_history_unbounded': lambda ctx: (
        interview_open_search(ctx),
        [interview_submit_search(ctx, f'seed{i}{int(time.time())%100000}') for i in range(60)]),
    'ytmusic_history_json_parse_per_row': lambda ctx: ytmusic_seed_history(ctx, plays=27),
    'sheafreader_article_list_foreach': lambda ctx: sheaf_add_feeds(ctx, 4),
    'sheafreader_extract_tag_tolowercase': lambda ctx: sheaf_add_feeds(ctx, 3),
    'sheafreader_insert_duplicate_exception': lambda ctx: sheaf_add_feeds(ctx, 3),
    'sheafreader_refresh_feeds_sequential': lambda ctx: sheaf_add_feeds(ctx, 10),
    'sheafreader_unread_counts_n_plus_1': lambda ctx: sheaf_add_feeds(ctx, 4),
})
