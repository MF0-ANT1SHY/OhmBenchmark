import time

from hypium import BY

from hapray.core.perf_testcase import PerfTestCase


class PerfLoad_browser_0020(PerfTestCase):
    CASE_ID = 'browser_history_delete_no_transaction'

    def __init__(self, controllers):
        self.TAG = self.__class__.__name__
        super().__init__(self.TAG, controllers)

        self._app_package = 'com.example.nanvision'
        self._app_name = '小狐狸浏览器'
        self._ability = 'EntryAbility'
        # 原始采集设备的屏幕尺寸（Pura 70）
        self.source_screen_width = 1256
        self.source_screen_height = 2760

    @property
    def app_package(self) -> str:
        return self._app_package

    @property
    def app_name(self) -> str:
        return self._app_name

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

    def process(self):
        self.driver.swipe_to_home()

        def step1():
            self.run_bench()

        self.execute_performance_step('浏览器-执行清空全部浏览记录', 20, step1)
