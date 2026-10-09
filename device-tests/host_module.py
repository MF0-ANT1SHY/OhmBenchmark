#!/usr/bin/env python3
"""Print the HAP module directory a host installs under haps/.

Verified against the device: interviewapp -> phone, browser -> entry, sheafreader -> entry,
weatherassistant -> alatus. The module that becomes the HAP is the *product* module, so
library modules (calendar, basic, constants, uicomponents) are excluded.

Usage: python3 device-tests/host_module.py CASE_ID
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIBRARY_MODULES = {'calendar', 'basic', 'constants', 'uicomponents'}


def product_module_dir(case_id: str) -> Path | None:
    """The product module directory that becomes the HAP."""
    spec = json.loads((REPO / 'cases' / case_id / 'case.json').read_text(encoding='utf-8'))
    root = Path(spec['host_app'].get('local_path', ''))
    if not root.exists():
        return None
    cands = sorted(root.glob('products/*'))
    if not cands:
        cands = sorted(p for p in root.glob('*') if (p / 'src/main/module.json5').exists())
    cands = [c for c in cands if c.name not in LIBRARY_MODULES]
    for c in cands:
        if c.name == 'entry':
            return c
    return cands[0] if cands else None


def host_ability(case_id: str) -> str:
    """The ability the collector must start, taken from the product module itself."""
    mod = product_module_dir(case_id)
    if mod is None:
        return 'EntryAbility'
    spec = mod / 'src/main/module.json5'
    if not spec.exists():
        return 'EntryAbility'
    m = re.search(r'"mainElement"\s*:\s*"([^"]+)"', spec.read_text(encoding='utf-8'))
    return m.group(1) if m else 'EntryAbility'


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
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if len(sys.argv) > 2 and sys.argv[2] == '--ability':
        print(host_ability(sys.argv[1]))
    else:
        print(host_module(sys.argv[1]))
