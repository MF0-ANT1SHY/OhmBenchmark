#!/usr/bin/env python3
"""Emit HapRay testcases from explicit external UI plans, without app-side gates."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate(case_dir):
    case = json.loads((case_dir / "case.json").read_text())
    name = case["testcase"]["name"]
    plan = case_dir / "testcase" / f"{name}.workload.json"
    if not plan.exists():
        return False
    spec = json.loads(plan.read_text())
    description = spec["description"]
    module = (ROOT / "tools/ui_driver.py").read_text().split("\ndef main():", 1)[0]
    (case_dir / "testcase/workload_driver.py").write_text(module)
    testcase = f'''from pathlib import Path
import json

from hapray.core.perf_testcase import PerfTestCase
from .workload_driver import UI


class {name}(PerfTestCase):
    def __init__(self, controllers):
        self.TAG = self.__class__.__name__
        super().__init__(self.TAG, controllers)
        self._plan = json.loads(Path(__file__).with_suffix('.workload.json').read_text())
        self._app_package = self._plan['bundle']
        self._app_name = {case['host_app']['name']!r}
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
        ui.run([{{'op': 'stop'}}, {{'op': 'launch'}}])
        ui.run(self._plan['setup'])
        self.execute_performance_step(
            {description!r}, {case['collection']['step_duration_s']!r},
            lambda: ui.run(self._plan['measured']))
        ui.run(self._plan['verify'])
'''
    (case_dir / case["testcase"]["py_file"]).write_text(testcase)
    return True


if __name__ == "__main__":
    count = sum(generate(p.parent) for p in sorted((ROOT / "cases").glob("*/case.json")))
    print(f"{count}/30 external UI testcases generated")
