"""External native scheduler recording for an ordinary reader refresh."""
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

from rss_refresh_progress import read_state, complete_refresh, REFRESH_BUTTON

TRACE_ROOT = '/sys/kernel/tracing'
BUNDLE = 'com.sheafreader.hm'


def cpu_set(raw):
    result = set()
    for piece in raw.strip().split(','):
        if not re.fullmatch(r'\d+(?:-\d+)?', piece):
            raise ValueError('invalid native CPU mask')
        limits = list(map(int, piece.split('-')))
        first, last = limits[0], limits[-1]
        if first > last or last > 255:
            raise ValueError('invalid native CPU range')
        result.update(range(first, last + 1))
    return sorted(result)


def process(shell):
    pid = shell('pidof ' + BUNDLE).strip()
    if not pid.isdigit():
        raise ValueError('one live reader process is required')
    command = shell(f'cat /proc/{pid}/cmdline')
    stat = shell(f'cat /proc/{pid}/stat')
    if BUNDLE not in command or ')' not in stat:
        raise ValueError('reader PID provenance is not proven')
    ticks = stat.rsplit(')', 1)[1].split()[19]
    if not ticks.isdigit():
        raise ValueError('invalid native process start ticks')
    return {'pid': int(pid), 'command': command, 'start_ticks': int(ticks)}


def bracket_cpus(shell, cpus):
    # Observer-only affinity changes happen outside the measured markers. They
    # ensure a sched transition before/after the window even on idle CPUs.
    for cpu in cpus:
        result = shell(f"taskset {1 << cpu:x} /system/bin/sh -c 'echo READY'").strip()
        if result != 'READY':
            raise ValueError('native observer affinity failed: ' + result)


def record(ui, plan, folder):
    if plan['bundle'] != BUNDLE:
        raise ValueError('reader trace recorder provided to a different app')
    shell = ui.shell
    if shell('pidof hiperf').strip() or shell(f'cat {TRACE_ROOT}/tracing_on').strip() != '0':
        raise ValueError('another native profiler is active; no device state changed')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    device_file = f'/data/local/tmp/trace-{token}.htrace'
    receipt = {'status': 'FAIL', 'marker_token': token, 'performance_verified': False}
    owned = False
    acknowledged = False
    original_buffer = None
    try:
        ui.run([{'op': 'stop'}, {'op': 'launch'}])
        ui.run(plan['setup'])
        ui.find(REFRESH_BUTTON, 120)
        before = read_state(shell)
        initial = process(shell)
        cpus = cpu_set(shell('cat /sys/devices/system/cpu/online'))
        receipt['process_before'] = initial
        receipt['online_cpus_before'] = cpus
        original_buffer = shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip()
        if not original_buffer.isdigit():
            raise ValueError('native trace buffer configuration is unavailable')
        receipt['buffer_size_kb_before'] = int(original_buffer)
        if shell(f'cat {TRACE_ROOT}/tracing_on').strip() != '0':
            raise ValueError('a native trace began during UI setup; it is not ours')
        started = shell('hitrace --trace_begin --text --trace_clock boot -b 65536 sched')
        receipt['trace_begin_output'] = started
        if 'OpenRecording done' not in started:
            raise ValueError('native trace start was not acknowledged')
        owned = True
        acknowledged = True
        if shell(f'cat {TRACE_ROOT}/tracing_on').strip() != '1':
            raise ValueError('our acknowledged native trace is not running')
        receipt['clock_before'] = shell(f'cat {TRACE_ROOT}/trace_clock').strip()
        if '[boot]' not in receipt['clock_before']:
            raise ValueError('native trace does not use the required boot clock')
        bracket_cpus(shell, cpus)
        output = shell(f"echo 'W:{token}:begin' > {TRACE_ROOT}/trace_marker")
        if output.strip():
            raise ValueError('native begin marker write failed: ' + output)
        receipt['action_start_monotonic'] = time.monotonic()
        ui.run(plan['measured'])
        ui.run(plan['verify'])
        receipt['reader_refresh'] = complete_refresh(ui, before)
        receipt['action_end_monotonic'] = time.monotonic()
        output = shell(f"echo 'W:{token}:end' > {TRACE_ROOT}/trace_marker")
        if output.strip():
            raise ValueError('native end marker write failed: ' + output)
        bracket_cpus(shell, cpus)
        receipt['process_after'] = process(shell)
        receipt['online_cpus_after'] = cpu_set(shell('cat /sys/devices/system/cpu/online'))
        receipt['clock_after'] = shell(f'cat {TRACE_ROOT}/trace_clock').strip()
        if (receipt['process_after'] != initial or receipt['online_cpus_after'] != cpus
                or receipt['clock_after'] != receipt['clock_before']):
            raise ValueError('process, CPU mask or clock changed during the native trace')
        receipt['saved_tgids'] = shell(f'cat {TRACE_ROOT}/saved_tgids')
        receipt['trace_finish_output'] = shell('hitrace --trace_finish --text -o ' + device_file)
        if shell(f'cat {TRACE_ROOT}/tracing_on').strip() != '0':
            raise ValueError('our native trace did not stop')
        owned = False
        subprocess.run(['hdc', 'file', 'recv', device_file, str(folder/'trace.htrace')],
                       check=True, capture_output=True, timeout=180)
        if not (folder/'trace.htrace').stat().st_size:
            raise ValueError('native trace file is empty')
        receipt['pids'] = [initial['pid']]
        receipt['status'] = 'CAPTURED'
    except Exception as exc:
        receipt['error'] = str(exc)
    finally:
        if owned:
            try:
                receipt['cleanup_output'] = shell('hitrace --trace_finish_nodump')
            except Exception as exc:
                receipt['cleanup_error'] = str(exc)
        if acknowledged and original_buffer is not None:
            try:
                if shell(f'cat {TRACE_ROOT}/tracing_on').strip() != '0':
                    raise ValueError('native trace is still active; buffer configuration not touched')
                changed = shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip()
                if changed != original_buffer:
                    output = shell(f'echo {original_buffer} > {TRACE_ROOT}/buffer_size_kb')
                    if output.strip():
                        raise ValueError('native buffer restoration failed: ' + output)
                receipt['buffer_size_kb_after'] = int(shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip())
                if receipt['buffer_size_kb_after'] != int(original_buffer):
                    raise ValueError('native buffer configuration did not restore')
            except Exception as exc:
                receipt['status'] = 'FAIL'
                receipt['configuration_cleanup_error'] = str(exc)
        (folder/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt
