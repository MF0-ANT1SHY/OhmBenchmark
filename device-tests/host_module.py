#!/usr/bin/env python3
"""Print the HAP module directory a host installs under haps/.

Verified against the device: interviewapp -> phone, browser -> entry, sheafreader -> entry,
weatherassistant -> alatus. The module that becomes the HAP is the *product* module, so
library modules (calendar, basic, constants, uicomponents) are excluded.

Usage: python3 device-tests/host_module.py CASE_ID
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIBRARY_MODULES = {'calendar', 'basic', 'constants', 'uicomponents'}


def host_module(case_id: str) -> str:
    spec = json.loads((REPO / 'cases' / case_id / 'case.json').read_text(encoding='utf-8'))
    root = Path(spec['host_app'].get('local_path', ''))
    if not root.exists():
        return 'entry'
    cands = [m.parts[-4] for m in root.glob('products/*/src/main/module.json5')]
    if not cands:
        cands = [m.parts[-4] for m in root.glob('*/src/main/module.json5')]
    cands = [c for c in cands if c not in LIBRARY_MODULES]
    if 'entry' in cands:
        return 'entry'
    return sorted(cands)[0] if cands else 'entry'


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(host_module(sys.argv[1]))
