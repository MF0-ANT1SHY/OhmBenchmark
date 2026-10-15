"""Bounded external HMFS recording with evaluator-only per-CPU markers."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

from native_trace_record import cpu_set
from native_file_writes import verify_retention

ROOT = '/sys/kernel/tracing'


def markers(shell, token, side, cpus):
    commands = [f"taskset {1 << cpu:x} /system/bin/sh -c 'echo F:{token}:{side}:{cpu} > {ROOT}/trace_marker'"
                for cpu in cpus]
    result = shell(' && '.join(commands))
    if result.strip():
        raise ValueError('native filesystem retention marker write failed: '+result)


def record(shell, action, directory, buffer_kb=16384):
    if type(buffer_kb) is not int or not 4096 <= buffer_kb <= 131072:
        raise ValueError('invalid bounded native trace buffer')
    for name in ('hiperf','hiprofiler_cmd','hiprofilerd','native_daemon'):
        if shell('pidof '+name).strip():
            raise ValueError('another native profiler is live')
    if shell('cat '+ROOT+'/tracing_on').strip() != '0' or shell('cat '+ROOT+'/events/enable').strip() != '0':
        raise ValueError('another native trace is configured or live')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    token = uuid.uuid4().hex
    device_file = '/data/local/tmp/hmfs-trace-'+token
    receipt = {'status':'FAIL','token':token,'app_injection':False,'performance_accepted':False}
    original = shell('cat '+ROOT+'/buffer_size_kb').strip()
    if not original.isdigit():
        raise ValueError('original native trace buffer unavailable')
    receipt['buffer_size_before'] = original
    owned = False
    try:
        cpus = cpu_set(shell('cat /sys/devices/system/cpu/online'))
        receipt['cpus_before'] = cpus
        receipt['begin_output'] = shell(f'hitrace --trace_begin --trace_clock boot -b {buffer_kb} hmfs')
        if 'OpenRecording done' not in receipt['begin_output']:
            raise ValueError('native file trace start was not acknowledged')
        owned = True
        if shell('cat '+ROOT+'/tracing_on').strip() != '1':
            raise ValueError('acknowledged native file trace is not live')
        markers(shell,token,'begin',cpus)
        receipt['action_start_monotonic'] = time.monotonic()
        receipt['action'] = action()
        receipt['action_end_monotonic'] = time.monotonic()
        markers(shell,token,'end',cpus)
        receipt['cpus_after'] = cpu_set(shell('cat /sys/devices/system/cpu/online'))
        if cpus != receipt['cpus_after']:
            raise ValueError('online CPU set changed')
        receipt['finish_output'] = shell('hitrace --trace_finish -o '+device_file)
        if shell('cat '+ROOT+'/tracing_on').strip() != '0':
            raise ValueError('owned native file trace did not stop')
        owned = False
        subprocess.run(['hdc','file','recv',device_file,str(directory/'trace.txt')],
                       check=True,capture_output=True,timeout=180)
        raw = (directory/'trace.txt').read_bytes()
        receipt['trace_sha256'] = hashlib.sha256(raw).hexdigest()
        receipt['retention'] = verify_retention(raw.decode('utf-8'),token,cpus)
        receipt['status'] = 'NATIVE_FILE_TRACE_CAPTURED'
    except Exception as exc:
        receipt['error'] = str(exc)
        if getattr(exc, 'observation', None) is not None:
            receipt['failure_observation'] = exc.observation
        # Preserve the original partial trace even if the business action or
        # retention check failed. It is diagnostic evidence, never a pass.
        if owned:
            try:
                receipt['failure_finish_output'] = shell('hitrace --trace_finish -o '+device_file)
                if shell('cat '+ROOT+'/tracing_on').strip() != '0':
                    raise ValueError('failed-action trace remains active')
                owned = False
                subprocess.run(['hdc','file','recv',device_file,str(directory/'failure-trace.txt')],
                               check=True,capture_output=True,timeout=180)
                receipt['failure_trace_sha256'] = hashlib.sha256((directory/'failure-trace.txt').read_bytes()).hexdigest()
            except Exception as capture_error:
                receipt['failure_trace_error'] = str(capture_error)
    finally:
        if owned:
            receipt['cleanup_output'] = shell('hitrace --trace_finish_nodump')
        receipt['tracing_on_after'] = shell('cat '+ROOT+'/tracing_on').strip()
        receipt['events_enabled_after'] = shell('cat '+ROOT+'/events/enable').strip()
        if receipt['tracing_on_after'] != '0' or receipt['events_enabled_after'] != '0':
            receipt['status'] = 'FAIL'
            receipt['cleanup_error'] = 'native tracing remains active/configured; inspect before more work'
        else:
            shell('echo '+original+' > '+ROOT+'/buffer_size_kb')
            receipt['buffer_size_after'] = shell('cat '+ROOT+'/buffer_size_kb').strip()
            if receipt['buffer_size_after'] != original:
                receipt['status'] = 'FAIL'
                receipt['cleanup_error'] = 'native trace buffer did not restore'
        shell('rm -f '+device_file)
        for path in directory.iterdir():
            path.chmod(0o600)
        (directory/'capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
        (directory/'capture.json').chmod(0o600)
    return receipt
