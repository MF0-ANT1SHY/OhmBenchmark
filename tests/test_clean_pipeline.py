import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_clean_app import audit_source, findings
from ui_driver import UI


class CleanPipelineTests(unittest.TestCase):
    def test_retired_and_neutralized_probe_protocols_are_rejected(self):
        for text in (
            "ohmScanIndexOf(item, index)", "ohmCtrA++", "'ohm-status.json'",
            "want.parameters?.bench", "want.parameters['bench']",
            "want.parameters?.['bench']", "'OHMB/' + name", "'WORKLOAD/count'",
        ):
            with self.subTest(text=text):
                self.assertTrue(findings(text))

    def test_original_business_operations_are_not_removed(self):
        self.assertFalse(findings("this.list.indexOf(item); JSON.parse(item); font.registerFont(options);"))

    def test_exact_tree_identity_detects_a_new_anonymous_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            def commit(text):
                (repo / "main.ets").write_text(text)
                subprocess.run(["git", "-C", tmp, "add", "main.ets"], check=True)
                subprocess.run(["git", "-C", tmp, "-c", "user.name=Test", "-c", "user.email=test@localhost",
                                "commit", "-qm", "state"], check=True)
                return audit_source(repo, "HEAD")
            original = commit("export function run(): number { return 1; }")
            renamed = commit("let a=0; export function run(): number { a++; return 1; }")
            self.assertTrue(original["passed"])
            self.assertTrue(renamed["passed"])  # Name scanning alone is NOT the guarantee.
            self.assertNotEqual(original["tree"], renamed["tree"])

    def test_ui_target_cannot_come_from_another_app(self):
        layout = {"children": [
            {"attributes": {"bundleName": "wrong.app"}, "children": [
                {"attributes": {"text": "Continue", "bounds": "[0,0][10,10]"}}]},
            {"attributes": {"bundleName": "target.app"}, "children": [
                {"attributes": {"text": "Continue", "bounds": "[20,20][30,30]"}}]},
        ]}
        ui = UI(lambda command: "", "target.app")
        ui.layout = lambda: layout
        self.assertEqual(ui.center(ui.find({"text": "Continue"}, timeout=0)), (25,25))
        with self.assertRaises(RuntimeError):
            ui.find({"text": "Missing"}, timeout=0)

    def test_profiler_cannot_silently_swallow_failed_actions(self):
        ui = UI(lambda command: '', 'target.app')
        def swallowing_execute(description, duration, action, **kwargs):
            try:
                action()
            except Exception:
                pass
        with self.assertRaisesRegex(RuntimeError, 'workload failed'):
            ui.profiled(swallowing_execute, 'screen', 10, [{'op':'invalid'}])

    def test_truncated_capture_cannot_pass(self):
        ui = UI(lambda command: '', 'target.app')
        def execute(description, duration, action, **kwargs):
            action()
        with patch('ui_driver.time.monotonic', side_effect=[100,112]):
            with self.assertRaisesRegex(RuntimeError, 'capture window'):
                ui.profiled(execute, 'screen', 10, [])


if __name__ == "__main__":
    unittest.main()
