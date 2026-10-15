from pathlib import Path
import json
import importlib.util

from hapray.core.perf_testcase import PerfTestCase

# DeviceTest may load testcase files without a Python package context.
_spec = importlib.util.spec_from_file_location('external_workload_driver',
    Path(__file__).with_name('workload_driver.py'))
_driver_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_driver_module)
UI = _driver_module.UI


class PerfLoad_interviewapp_0010(PerfTestCase):
    def __init__(self, controllers):
        self.TAG = self.__class__.__name__
        super().__init__(self.TAG, controllers)
        self._plan = json.loads(Path(__file__).with_suffix('.workload.json').read_text())
        self._app_package = self._plan['bundle']
        self._app_name = 'interview-handbook-project (面试通)'
        self.source_screen_width = 1260
        self.source_screen_height = 2844

    @property
    def app_package(self) -> str:
        return self._app_package

    @property
    def app_name(self) -> str:
        return self._app_name

    def process(self):
        ui = UI(self.driver.shell, self._app_package, self._plan['ability'])
        ui.run([{'op': 'stop'}, {'op': 'launch'}])
        ui.run(self._plan['setup'])
        ui.profiled(self.execute_performance_step,
            'interview-handbook-project (面试通)页面操作', 120, self._plan['measured'])
        ui.run(self._plan['verify'])
