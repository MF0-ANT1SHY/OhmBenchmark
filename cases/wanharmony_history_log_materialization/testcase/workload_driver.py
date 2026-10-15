#!/usr/bin/env python3
"""External UI workload driver. Runs on the host, never in the application."""
import argparse
import json
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path


class UI:
    def __init__(self, shell, bundle=None, ability="EntryAbility"):
        self.shell, self.bundle, self.ability = shell, bundle, ability

    def layout(self):
        # HDC can return zero even when the device command failed. A unique path
        # prevents a failed dump from reusing a prior app's successful layout.
        path = f'/data/local/tmp/workload-layout-{uuid.uuid4().hex}.json'
        try:
            dump_output = self.shell(f"uitest dumpLayout -p {path}")
            raw = self.shell(f"cat {path}")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise json.JSONDecodeError(
                    f'Invalid fresh UI layout: dump={dump_output[:500]!r}, read={raw[:500]!r}',
                    exc.doc, exc.pos) from exc
        finally:
            self.shell(f'rm -f {path}')

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
        match_mode=selector.get('match','substring')
        if match_mode not in ('substring','exact','regex'):
            raise ValueError('invalid UI matching mode')
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
                    if match_mode=='exact':
                        return actual==str(value)
                    if match_mode=='regex':
                        return re.fullmatch(str(value),actual) is not None
                    return str(value) in actual
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

    def input(self, selector, value, cleared_text=''):
        if cleared_text not in ('','0'):
            raise ValueError('unsupported cleared input state')
        node=self.find(selector)
        x, y = self.center(node)
        if str(node.get('text','')):
            # uiInput inputText appends. Replace through ordinary keyboard input,
            # and verify clearing rather than silently searching "bluejazz".
            self.shell(f'uitest uiInput click {x} {y}')
            self.shell('uitest uiInput keyEvent 2072 2017')  # Ctrl+A
            self.shell('uitest uiInput keyEvent 2055')       # Backspace
            # Controlled Number(text) fields normalize the empty input to zero.
            # This must be explicitly declared; final value is still verified.
            if str(self.find(selector).get('text',''))!=cleared_text:
                raise RuntimeError('UI input did not clear the previous value')
        if value:
            self.shell(f"uitest uiInput inputText {x} {y} {shlex.quote(value)}")
        if str(self.find(selector).get('text',''))!=value:
            raise RuntimeError('UI input value does not match the requested text')

    def scroll_to(self, selector, max_swipes=20):
        if not isinstance(max_swipes,int) or max_swipes<0:
            raise ValueError('invalid swipe limit')
        bounds=list(map(int,re.findall(r'\d+',self.layout()['attributes']['bounds'])))
        x,bottom,top=round(bounds[2]*.5),round(bounds[3]*.78),round(bounds[3]*.3)
        reachable_bottom=round(bounds[3]*.85)
        for attempt in range(max_swipes+1):
            try:
                node=self.find(selector,timeout=0)
                # Native visibility includes rows covered by the bottom player.
                # Move them above that area; the swipe origin itself is too high
                # to serve as the tap boundary (a footer can sit just below it).
                if self.center(node)[1]<=reachable_bottom:
                    return
            except RuntimeError as exc:
                if not str(exc).startswith('UI target not found:'):
                    raise
            if attempt==max_swipes:
                raise RuntimeError(f'UI scroll target not reached: {selector}')
            self.shell(f'uitest uiInput swipe {x} {bottom} {x} {top} 1000')
            time.sleep(.4)

    def type_keys(self, selector, value, interval_ms=50):
        """Type ordinary lowercase keys in one device-side command.

        No intermediate layout dumps or text replacements interrupt the burst.
        Requested intervals do not prove application event delivery timing.
        """
        if (not isinstance(value, str) or not re.fullmatch(r'[a-z]{1,100}', value)
                or type(interval_ms) is not int or not 1 <= interval_ms <= 15000):
            raise ValueError('invalid keyboard typing burst')
        node = self.find(selector)
        if str(node.get('text', '')):
            raise RuntimeError('keyboard typing requires an empty input')
        x, y = self.center(node)
        self.shell(f'uitest uiInput click {x} {y}')
        parts = ['uinput -K']
        for index, letter in enumerate(value):
            if index:
                parts.append(f'-i {interval_ms}')
            key = 2017 + ord(letter) - ord('a')
            parts.append(f'-d {key} -u {key}')
        output = self.shell(' '.join(parts))
        if any(f'you raised the key {2017 + ord(letter) - ord("a")}' not in output
               for letter in value):
            raise RuntimeError('native keyboard injection did not confirm key release')
        if str(self.find(selector).get('text', '')) != value:
            raise RuntimeError('keyboard input does not match the requested text')

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
                self.input(action["selector"], action["value"], action.get('cleared_text',''))
            elif op == "type_keys":
                self.type_keys(action['selector'], action['value'], action.get('interval_ms', 50))
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
                if action.get('selector'):
                    bounds = self.find(action['selector'])['bounds']
                else:
                    bounds = self.layout()['attributes']['bounds']
                b = list(map(int, re.findall(r"\d+", bounds)))
                if len(b) != 4 or b[2] <= b[0] or b[3] <= b[1]:
                    raise ValueError('invalid swipe bounds')
                x = round((b[0]+b[2])*0.5)
                bottom = round(b[1]+(b[3]-b[1])*0.78)
                top = round(b[1]+(b[3]-b[1])*0.3)
                if action.get("direction", "up") == "down":
                    bottom, top = top, bottom
                for _ in range(action.get("count", 1)):
                    self.shell(f"uitest uiInput swipe {x} {bottom} {x} {top} 1000")
                    time.sleep(action.get("interval_s", 0.4))
            elif op == 'scroll_to':
                self.scroll_to(action['selector'],action.get('max_swipes',20))
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

