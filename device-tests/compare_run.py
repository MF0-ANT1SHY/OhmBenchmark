#!/usr/bin/env python3
"""Compare hw-instructions / task-clock / RSS-delta between unfixed and fixed run dirs.

Usage: compare_run.py <measurements-root>/<case>
"""
import json, re, statistics, sys
from pathlib import Path

case_dir = Path(sys.argv[1])


def stat_value(path: Path, name: str):
    if not path.exists():
        return None
    m = re.search(r'([\d,]+)\s+' + re.escape(name), path.read_text(errors='replace'))
    return int(m.group(1).replace(',', '')) if m else None


def vmrss_kb(path: Path):
    if not path.exists():
        return None
    m = re.search(r'VmRSS:\s+(\d+)\s+kB', path.read_text(errors='replace'))
    return int(m.group(1)) if m else None


for variant in ('unfixed', 'fixed'):
    instr, task, drss, elapsed, result = [], [], [], [], []
    for run in sorted((case_dir / variant).glob('run*')):
        st = run / 'perf-stat.txt'
        instr.append(stat_value(st, 'hw-instructions'))
        task.append(stat_value(st, 'sw-task-clock'))
        before, after = vmrss_kb(run / 'before.txt'), vmrss_kb(run / 'after.txt')
        if before is not None and after is not None:
            drss.append(after - before)
        rj = run / 'result.json'
        if rj.exists():
            res = json.loads(rj.read_text())
            elapsed.append(res.get('elapsed_ms'))
            result.append(res.get('result'))
    med = lambda v: statistics.median([x for x in v if x is not None]) if any(
        x is not None for x in v) else None
    print(f'{variant}:')
    print(f'  hw-instructions={instr}  median={med(instr)}')
    print(f'  sw-task-clock={task}  median={med(task)}')
    print(f'  drss_kb={drss}  median={med(drss)}')
    print(f'  elapsed_ms={elapsed}  result={result}')
