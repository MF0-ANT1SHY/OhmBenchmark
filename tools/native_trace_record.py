"""External native scheduler recording for verified ordinary app workloads."""
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

from rss_refresh_progress import read_state, complete_refresh, REFRESH_BUTTON

TRACE_ROOT = '/sys/kernel/tracing'
BUNDLE = 'com.sheafreader.hm'
BUFFER_KB = 131072


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


def process(shell, bundle=BUNDLE):
    if bundle not in (BUNDLE, 'org.example.wan.ohos'):
        raise ValueError('unsupported native scheduling target')
    pid = shell('pidof ' + bundle).strip()
    if not pid.isdigit():
        raise ValueError('one live reader process is required')
    command = shell(f'cat /proc/{pid}/cmdline')
    stat = shell(f'cat /proc/{pid}/stat')
    if command.split('\x00', 1)[0].strip() != bundle or ')' not in stat:
        raise ValueError('reader PID provenance is not proven')
    ticks = stat.rsplit(')', 1)[1].split()[19]
    if not ticks.isdigit():
        raise ValueError('invalid native process start ticks')
    return {'pid': int(pid), 'command': command, 'start_ticks': int(ticks)}


def bracket_cpus(shell, cpus):
    # Observer-only affinity changes happen outside the measured markers. They
    # ensure a sched transition before/after the window even on idle CPUs.
    if not cpus or any(type(cpu) is not int or not 0 <= cpu <= 255 for cpu in cpus):
        raise ValueError('invalid observer CPU set')
    # One transport round trip: serial HDC calls needlessly kept recording
    # after the end marker, consuming retention needed for the complete window.
    command = ' && '.join(f"taskset {1 << cpu:x} /system/bin/sh -c 'echo READY_{cpu}'" for cpu in cpus)
    result = shell(command).strip().splitlines()
    if result != [f'READY_{cpu}' for cpu in cpus]:
        raise ValueError('native observer affinity failed: ' + repr(result))


def record(ui, plan, folder, observer=None):
    if observer is None:
        if plan['bundle'] != BUNDLE:
            raise ValueError('reader trace recorder provided to a different app')
    elif (plan['bundle'] != 'org.example.wan.ohos'
          or observer.bundle != plan['bundle'] or observer.receipt_key != 'wan_history'):
        raise ValueError('native workload observer targets a different app')
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
        if observer is None:
            ui.find(REFRESH_BUTTON, 120)
            before = read_state(shell)
        else:
            before = observer.prepare(ui)
        initial = process(shell) if observer is None else process(shell, plan['bundle'])
        cpus = cpu_set(shell('cat /sys/devices/system/cpu/online'))
        receipt['process_before'] = initial
        receipt['online_cpus_before'] = cpus
        original_buffer = shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip()
        if not original_buffer.isdigit():
            raise ValueError('native trace buffer configuration is unavailable')
        receipt['buffer_size_kb_before'] = int(original_buffer)
        if shell(f'cat {TRACE_ROOT}/tracing_on').strip() != '0':
            raise ValueError('a native trace began during UI setup; it is not ours')
        started = shell(f'hitrace --trace_begin --trace_clock boot -b {BUFFER_KB} sched')
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
        recording_buffer = shell(f'cat {TRACE_ROOT}/buffer_size_kb').strip()
        if not recording_buffer.isdigit() or int(recording_buffer) <= 0:
            raise ValueError('effective native recording buffer is unavailable')
        receipt['requested_buffer_size_kb'] = BUFFER_KB
        receipt['recording_buffer_size_kb'] = int(recording_buffer)
        bracket_cpus(shell, cpus)
        output = shell(f"echo 'W:{token}:begin' > {TRACE_ROOT}/trace_marker")
        if output.strip():
            raise ValueError('native begin marker write failed: ' + output)
        receipt['action_start_monotonic'] = time.monotonic()
        ui.run(plan['measured'])
        ui.run(plan['verify'])
        if observer is None:
            receipt['reader_refresh'] = complete_refresh(ui, before)
        else:
            receipt[observer.receipt_key] = observer.complete(ui, before)
        receipt['action_end_monotonic'] = time.monotonic()
        output = shell(f"echo 'W:{token}:end' > {TRACE_ROOT}/trace_marker")
        if output.strip():
            raise ValueError('native end marker write failed: ' + output)
        bracket_cpus(shell, cpus)
        receipt['process_after'] = process(shell) if observer is None else process(shell, plan['bundle'])
        receipt['online_cpus_after'] = cpu_set(shell('cat /sys/devices/system/cpu/online'))
        receipt['clock_after'] = shell(f'cat {TRACE_ROOT}/trace_clock').strip()
        if (receipt['process_after'] != initial or receipt['online_cpus_after'] != cpus
                or receipt['clock_after'] != receipt['clock_before']):
            raise ValueError('process, CPU mask or clock changed during the native trace')
        receipt['saved_tgids'] = shell(f'cat {TRACE_ROOT}/saved_tgids')
        receipt['trace_finish_output'] = shell('hitrace --trace_finish -o ' + device_file)
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
        if getattr(exc, 'observation', None) is not None:
            receipt['failure_observation'] = exc.observation
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
