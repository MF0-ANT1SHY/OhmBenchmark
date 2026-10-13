#!/usr/bin/env python3
"""External UI workload driver. Runs on the host, never in the application."""
import argparse
import json
import re
import shlex
import subprocess
import time
from pathlib import Path


class UI:
    def __init__(self, shell, bundle=None, ability="EntryAbility"):
        self.shell, self.bundle, self.ability = shell, bundle, ability

    def layout(self):
        path = "/data/local/tmp/workload-layout.json"
        self.shell(f"uitest dumpLayout -p {path}")
        return json.loads(self.shell(f"cat {path}"))

    @staticmethod
    def nodes(layout, inherited_bundle=None):
        attributes = dict(layout.get("attributes", {}))
        bundle = attributes.get("bundleName") or inherited_bundle
        if bundle:
            attributes["bundleName"] = bundle
        yield attributes
        for child in layout.get("children", []):
            yield from UI.nodes(child, bundle)

    def find(self, selector, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            layout = self.layout()
            matches = []
            for node in self.nodes(layout):
                if node.get("visible") == "false" or node.get("enabled") == "false":
                    continue
                if self.bundle and node.get("bundleName") not in (None, "", self.bundle):
                    continue
                def matches_field(key, value):
                    actual = str(node.get(key, ''))
                    return actual == str(value) if selector.get('match') == 'exact' else str(value) in actual
                if all(matches_field(key,value) for key,value in selector.items() if key not in ('index','match')):
                    matches.append(node)
            index = selector.get("index", 0)
            if len(matches) > index:
                return matches[index]
            if time.monotonic() >= deadline:
                raise RuntimeError(f"UI target not found: {selector}")
            time.sleep(0.25)

    @staticmethod
    def center(node):
        numbers = list(map(int, re.findall(r"-?\d+", node["bounds"])))
        if len(numbers) != 4 or numbers[2] <= numbers[0] or numbers[3] <= numbers[1]:
            raise RuntimeError(f"invalid UI bounds: {node}")
        return (numbers[0]+numbers[2])//2, (numbers[1]+numbers[3])//2

    def tap(self, selector):
        x, y = self.center(self.find(selector))
        self.shell(f"uitest uiInput click {x} {y}")

    def input(self, selector, value):
        x, y = self.center(self.find(selector))
        self.shell(f"uitest uiInput inputText {x} {y} {shlex.quote(value)}")

    def run(self, actions):
        for action in actions:
            op = action["op"]
            if op == "launch":
                flags = action.get("flags")
                if flags is not None and (not isinstance(flags, int) or not 0 <= flags <= 0xffffffff):
                    raise ValueError("invalid activity launch flags")
                suffix = f" -f {flags}" if flags is not None else ""
                self.shell(f"aa start -a {shlex.quote(self.ability)} -b {shlex.quote(self.bundle)}" + suffix)
            elif op == "stop":
                self.shell(f"aa force-stop {shlex.quote(self.bundle)}")
            elif op == "tap":
                self.tap(action["selector"])
            elif op == "input":
                self.input(action["selector"], action["value"])
            elif op == "wait":
                self.find(action["selector"], action.get("timeout_s", 15))
            elif op == "pause":
                time.sleep(action["seconds"])
            elif op == "key":
                key = action["key"]
                if not re.fullmatch(r"Back|Home|Power|\d+", str(key)):
                    raise ValueError("invalid UI key")
                self.shell(f"uitest uiInput keyEvent {key}")
            elif op == "point":
                layout = self.layout()
                b = list(map(int, re.findall(r"\d+", layout["attributes"]["bounds"])))
                x, y = round(b[2]*action["x"]), round(b[3]*action["y"])
                self.shell(f"uitest uiInput click {x} {y}")
            elif op == "swipe":
                layout = self.layout()
                b = list(map(int, re.findall(r"\d+", layout["attributes"]["bounds"])))
                x, bottom, top = round(b[2]*0.5), round(b[3]*0.78), round(b[3]*0.3)
                if action.get("direction", "up") == "down":
                    bottom, top = top, bottom
                for _ in range(action.get("count", 1)):
                    self.shell(f"uitest uiInput swipe {x} {bottom} {x} {top} 1000")
                    time.sleep(action.get("interval_s", 0.4))
            elif op == "repeat":
                for _ in range(action["count"]):
                    self.run(action["actions"])
            else:
                raise ValueError(f"unsupported external action: {op}")

    def profiled(self, execute, description, duration, actions):
        """Fail after collection even when the profiler swallows action exceptions."""
        failures, elapsed, called = [], [], []
        def action():
            called.append(True)
            started = time.monotonic()
            try:
                self.run(actions)
            except Exception as exc:
                failures.append(exc)
                raise
            finally:
                elapsed.append(time.monotonic() - started)
        def launches(items):
            return any(item['op'] == 'launch' or
                       (item['op'] == 'repeat' and launches(item['actions'])) for item in items)
        execute(description, duration, action, sample_all_processes=launches(actions))
        if not called:
            raise RuntimeError('profiler did not execute the workload')
        if failures:
            raise RuntimeError('measured UI workload failed') from failures[0]
        if elapsed[0] > duration:
            raise RuntimeError(f'workload took {elapsed[0]:.2f}s, exceeding the {duration}s capture window')
        return elapsed[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--phase", choices=["setup", "measured", "verify"], default="measured")
    parser.add_argument("--remote", help="optional SSH alias of the WSL device workstation")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.remote:
        from remote_device import Remote
        remote = Remote(args.remote)
        shell = lambda command: remote.hdc(["shell", command])
    else:
        def shell(command):
            result = subprocess.run(["hdc", "shell", command], check=True,
                                    capture_output=True, text=True, timeout=90)
            return result.stdout
    ui = UI(shell, plan["bundle"], plan["ability"])
    if args.phase == "setup":
        shell(f"aa force-stop {shlex.quote(plan['bundle'])}")
        shell(f"aa start -a {shlex.quote(plan['ability'])} -b {shlex.quote(plan['bundle'])}")
    ui.run(plan.get(args.phase, []))


if __name__ == "__main__":
    main()
