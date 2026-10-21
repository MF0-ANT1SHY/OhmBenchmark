"""Native scheduler profile of ordinary startup and unread badge loading."""
import json
from pathlib import Path
import subprocess
import time
import uuid
from native_trace_record import TRACE_ROOT, BUNDLE, BUFFER_KB, cpu_set, process, bracket_cpus
from rss_refresh_progress import read_state, rows, verify_refresh, REFRESH_BUTTON
from reader_count_progress import visible_badges


def record(ui, plan, folder, expected):
    if plan['bundle'] != BUNDLE:
        raise ValueError('startup recording targets a different app')
    shell = ui.shell
    if shell('pidof hiperf').strip() or shell(f'cat {TRACE_ROOT}/tracing_on').strip() != '0':
        raise ValueError('another native profiler is active; no device state changed')
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    device_file = f'/data/local/tmp/trace-{token}.htrace'
    receipt = {'status': 'FAIL', 'marker_token': token, 'performance_verified': False}
    owned = False
    acknowledged = False
    original_buffer = None
    try:
        ui.run([{'op': 'stop'}])
        shell('power-shell wakeup')
        shell('uitest uiInput swipe 630 2300 630 500 600')
        cpus = cpu_set(shell('cat /sys/devices/system/cpu/online'))
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
        receipt['launch_output'] = shell('aa start -b com.sheafreader.hm -a EntryAbility')
        if 'start ability successfully' not in receipt['launch_output']:
            raise ValueError('normal application launch failed')
        initial = process(shell)
        receipt['process_before'] = initial
        ui.run(plan['verify'])
        ui.find({**REFRESH_BUTTON, 'enabled': 'true'}, 120)
        layout = ui.layout()
        receipt['reader_counts'] = {'layout': layout, 'badges': visible_badges(layout, expected)}
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
