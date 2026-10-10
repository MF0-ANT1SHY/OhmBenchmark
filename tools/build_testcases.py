#!/usr/bin/env python3
"""Generate the HapRay-format test case pair (.py + .json) for every case.

Each cases/<id>/testcase/ holds a PerfTestCase subclass in the exact format
SMAT-Lab/ArkAnalyzer-HapRay's perf_testing/hapray/testcases/ uses, plus its
.json driver descriptor. Drop both files into
perf_testing/hapray/testcases/<bundle>/ and select with --run_testcases <name>.

Trigger modes:
  bench    - the measured step runs the app's `--ps bench <case>` entry
             (harness patch applied at build time) and polls ohm-status.json.
  relaunch - the bench entry runs once unmeasured to seed state, then the
             measured step is a cold relaunch of the app.
  ui       - the measured step is driven through hypium UI actions.

Usage: python3 tools/build_testcases.py          # regenerate all
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- per-case spec
# name/class is <type>_<scene>_<serial>; serials are per-scene, manifest order.
APP_NAME = {
    'browser': '小狐狸浏览器', 'cloudmusic': '仿网易云音乐', 'interviewapp': '面试通',
    'jingmo': '京墨文库', 'sepweather': 'SepWeather', 'sheafreader': '束阅',
    'wanharmony': 'WanHarmony', 'weatherassistant': 'WeatherAssistant',
    'ytmusic': 'YoutubeMusic',
}
ABILITY = {'interviewapp': 'PhoneAbility', 'weatherassistant': 'AlatusAbility'}
SCENE_CN = {
    'browser': '浏览器', 'cloudmusic': '网易云音乐', 'interviewapp': '面试通',
    'jingmo': '京墨文库', 'sepweather': 'SepWeather', 'sheafreader': '束阅',
    'wanharmony': 'WanAndroid', 'weatherassistant': '天气助手', 'ytmusic': 'YoutubeMusic',
}

# (case_id, type, serial, trigger, step_description, duration_s, step_extra)
# step_extra: python source inserted inside the measured step after the trigger.
SPECS = [
    ('browser_eager_history_load', 'PerfLoad', '0010', 'relaunch',
     '冷启动并等待首页渲染完成', 15, None),
    ('browser_history_delete_no_transaction', 'PerfLoad', '0020', 'bench',
     '执行清空全部浏览记录', 20, None),
    ('browser_history_list_foreach', 'PerfLoad', '0030', 'bench_ui',
     '打开浏览记录页并上下滑动列表', 20,
     "self.touch_by_text('历史记录', 1)\n"
     "        self.swipes_up(3, 1)\n"
     "        self.swipes_down(3, 1)"),
    ('browser_insert_date_lookup_cache', 'PerfLoad', '0040', 'bench',
     '连续保存浏览记录', 30, None),
    ('cloudmusic_indexof_in_render', 'PerfLoad', '0010', 'bench_ui',
     '打开歌单并匀速滑动歌曲列表', 25,
     'self.swipes_up(5, 1)\n        self.swipes_down(5, 1)'),
    ('cloudmusic_local_song_memory_filter', 'PerfLoad', '0020', 'bench',
     '本地音乐页重复提交关键字搜索', 20, None),
    ('cloudmusic_play_time_high_frequency_update', 'PerfLoad', '0030', 'bench',
     '播放页静置播放60秒', 70, None),
    ('cloudmusic_search_result_foreach', 'PerfLoad', '0040', 'bench_ui',
     '搜索结果页加载多页并上下滑动', 30,
     'self.swipes_up(5, 1)\n        self.swipes_down(5, 1)'),
    ('cloudmusic_songcard_artists_concat', 'PerfLoad', '0050', 'bench_ui',
     '大歌单连续滑动30秒', 35,
     'self.swipes_up(5, 1)\n        self.swipes_down(5, 1)'),
    ('interviewapp_response_log_full_stringify', 'PerfLoad', '0010', 'bench',
     '连续触发大列表接口响应', 30, None),
    ('interviewapp_search_history_sync_flush', 'PerfLoad', '0020', 'bench',
     '快速连续提交搜索词', 30, None),
    ('interviewapp_search_history_unbounded', 'MemLoad', '0030', 'bench',
     '批量写入搜索历史后打开搜索页', 20, None),
    ('jingmo_dataset_import_no_transaction', 'PerfLoad', '0010', 'bench',
     '触发数据集同步导入', 60, None),
    ('jingmo_random_poem_orderby_random', 'PerfLoad', '0020', 'bench',
     '随机一首页面连续刷新', 20, None),
    ('jingmo_sync_page_reimport', 'PerfLoad', '0030', 'bench',
     '再次打开数据同步页', 15, None),
    ('sepweather_font_register_per_page', 'PerfLoad', '0010', 'bench',
     '反复进出主页触发字体注册', 30, None),
    ('sheafreader_article_list_foreach', 'PerfLoad', '0010', 'bench_ui',
     '打开全部文章并多次加载后滑动', 40,
     'self.swipes_up(5, 1)\n        self.swipes_down(5, 1)'),
    ('sheafreader_extract_tag_tolowercase', 'PerfLoad', '0020', 'bench',
     '刷新全部订阅并解析长正文', 40, None),
    ('sheafreader_insert_duplicate_exception', 'PerfLoad', '0030', 'bench',
     '在已导入文章上再次全部刷新', 60, None),
    ('sheafreader_refresh_feeds_sequential', 'PerfLoad', '0040', 'bench',
     '触发全部订阅刷新', 60, None),
    ('sheafreader_unread_counts_n_plus_1', 'PerfLoad', '0050', 'bench',
     '触发侧栏订阅未读计数刷新', 30, None),
    ('wanharmony_history_log_materialization', 'PerfLoad', '0010', 'bench',
     '打开浏览历史页触发完整序列化', 30, None),
    ('wanharmony_html_decode_per_render', 'PerfLoad', '0020', 'bench_ui',
     '首页文章列表连续滑动', 35,
     'self.swipes_up(5, 1)\n        self.swipes_down(5, 1)'),
    ('wanharmony_persisted_home_list_growth', 'MemLoad', '0030', 'bench_ui',
     '首页无限加载触发全量持久化', 60,
     'self.swipes_up(5, 1)'),
    ('wanharmony_web_progress_log_storm', 'PerfLoad', '0040', 'bench',
     '连续打开文章页触发进度日志', 30, None),
    ('weatherassistant_http_session_leak', 'MemLoad', '0010', 'bench',
     '连续城市刷新触发HTTP会话泄漏', 60, None),
    ('weatherassistant_remote_weather_icons', 'PerfLoad', '0020', 'relaunch_noseed',
     '冷启动渲染天气面板并切换城市', 25, None),
    ('ytmusic_current_playing_timeupdate', 'PerfLoad', '0010', 'bench',
     '正在播放页静置播放60秒', 70, None),
    ('ytmusic_history_json_parse_per_row', 'PerfLoad', '0020', 'bench_ui',
     '打开历史记录页并滑动浏览', 15,
     'self.swipes_up(3, 1)\n        self.swipes_down(3, 1)'),
    ('ytmusic_search_no_debounce', 'PerfLoad', '0030', 'ui',
     '搜索框逐字输入关键字并提交', 30, None),
]

HEADER = '''import time

from hypium import BY

from hapray.core.perf_testcase import PerfTestCase


'''

HELPERS = '''
    # ------------------------------------------------------ OhmBenchmark bench
    @property
    def files_dir(self) -> str:
        if not hasattr(self, '_files_dir'):
            out = self.driver.shell(f'ls /data/app/el2/100/base/{self.app_package}/haps')
            module = out.strip().splitlines()[0]
            self._files_dir = f'/data/app/el2/100/base/{self.app_package}/haps/{module}/files'
        return self._files_dir

    def wait_state(self, state: str, timeout: int = 180):
        deadline = time.monotonic() + timeout
        status = f'{self.files_dir}/ohm-status.json'
        while time.monotonic() < deadline:
            if f'"state":"{state}"' in self.driver.shell(f'cat {status}'):
                return
            time.sleep(0.25)
        raise TimeoutError(f'{state} not reached: {self.driver.shell(f"cat {status}")}')

    def run_bench(self, timeout: int = 300):
        """Drive the workload through the app's `--ps bench <case>` entry."""
        self.driver.shell(f'aa force-stop {self.app_package}')
        self.driver.shell(f'rm -f {self.files_dir}/ohm-status.json {self.files_dir}/ohm-go')
        self.driver.shell(f'aa start -a {self._ability} -b {self.app_package}')
        self.driver.shell(f'aa start -a {self._ability} -b {self.app_package} --ps bench {self.CASE_ID}')
        self.wait_state('ready', timeout)
        self.driver.shell(f'touch {self.files_dir}/ohm-go')
        self.wait_state('done', timeout)

    def relaunch(self):
        """Cold relaunch: the measured window is app startup itself."""
        self.driver.shell(f'aa force-stop {self.app_package}')
        self.driver.shell(f'aa start -a {self._ability} -b {self.app_package}')
'''


def emit(spec):
    case_id, typ, serial, trigger, desc, dur, extra = spec
    scene = case_id.split('_')[0]
    name = f'{typ}_{scene}_{serial}'
    cls = [HEADER]
    cls.append(f'''class {name}(PerfTestCase):
    CASE_ID = '{case_id}'

    def __init__(self, controllers):
        self.TAG = self.__class__.__name__
        super().__init__(self.TAG, controllers)

        self._app_package = '{json.loads((ROOT / 'cases' / case_id / 'case.json').read_text())['host_app']['bundle_name']}'
        self._app_name = '{APP_NAME[scene]}'
        self._ability = '{ABILITY.get(scene, 'EntryAbility')}'
        # 原始采集设备的屏幕尺寸（Pura 70）
        self.source_screen_width = 1256
        self.source_screen_height = 2760

    @property
    def app_package(self) -> str:
        return self._app_package

    @property
    def app_name(self) -> str:
        return self._app_name
''')
    cls.append(HELPERS)
    body = f'''
    def process(self):
        self.driver.swipe_to_home()
'''
    if trigger == 'relaunch':
        body += f'''
        # 先用 bench 入口准备数据（不计时），再冷启动采集启动阶段数据
        self.run_bench()

        def step1():
            self.relaunch()
            time.sleep({dur})

        self.execute_performance_step('{SCENE_CN[scene]}-{desc}', {dur}, step1)
'''
    elif trigger == 'relaunch_noseed':
        body += f'''
        def step1():
            self.relaunch()
            time.sleep({dur})

        self.execute_performance_step('{SCENE_CN[scene]}-{desc}', {dur}, step1)
'''
    elif trigger == 'ui':
        body += f'''
        def step1():
            self.driver.shell(f'aa force-stop {{self.app_package}}')
            self.driver.shell(f'aa start -a {{self._ability}} -b {{self.app_package}}')
            self.driver.wait(8)
            # 进入搜索页并逐字输入：每个字符都触发一次 onChange
            self.touch_by_text('搜索', 2)
            self.driver.input_text(BY.type('TextInput'), 'harmony performance')
            self.driver.wait(3)

        self.execute_performance_step('{SCENE_CN[scene]}-{desc}', {dur}, step1)
'''
    elif trigger == 'bench_ui':
        body += f'''
        def step1():
            self.run_bench()
            {extra}

        self.execute_performance_step('{SCENE_CN[scene]}-{desc}', {dur}, step1)
'''
    else:  # bench
        body += f'''
        def step1():
            self.run_bench()

        self.execute_performance_step('{SCENE_CN[scene]}-{desc}', {dur}, step1)
'''
    cls.append(body)
    return name, ''.join(cls)


def main():
    for spec in SPECS:
        case_id, typ = spec[0], spec[1]
        name, source = emit(spec)
        tdir = ROOT / 'cases' / case_id / 'testcase'
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f'{name}.py').write_text(source, encoding='utf-8')
        descriptor = {
            'description': case_id,
            'environment': [{'type': 'device', 'label': 'phone'}],
            'driver': {'type': 'DeviceTest', 'py_file': [f'{name}.py']},
            'kits': [],
        }
        (tdir / f'{name}.json').write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
        print(f'{case_id}: {name}')


if __name__ == '__main__':
    main()
