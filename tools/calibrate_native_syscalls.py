#!/usr/bin/env python3
"""Run the external, own-child-only syscall capability probe while idle.

This does not attach to an app and cannot satisfy a case's write-volume oracle.
"""
import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path

from remote_device import Remote

ROOT = Path(__file__).resolve().parents[1]


def calibrate(remote, binary, output, arguments=()):
    if tuple(arguments) not in ((), ('--nr-phase',), ('--raw-registers',)):
        raise ValueError('only the explicit own-child calibration modes are allowed')
    if output.exists():
        raise FileExistsError('preserve previous native calibration evidence')
    if binary.read_bytes()[:4] != b'\x7fELF':
        raise ValueError('expected a compiled native ELF probe')
    # An idle-device guard is checked before deployment, not merely assumed
    # from a coordinator's stale status file.
    for name in ('hiperf', 'hiprofiler_cmd', 'hiprofilerd', 'native_daemon'):
        if remote.hdc(['shell', 'pidof ' + name]).strip():
            raise RuntimeError('wait for the existing profiler: ' + name)
    if remote.hdc(['shell', 'cat /sys/kernel/tracing/tracing_on']).strip() != '0':
        raise RuntimeError('wait for the existing native trace')
    token = uuid.uuid4().hex
    remote_binary = '/home/research/ohm-clean/syscall-probe/' + token
    device_binary = '/data/local/tmp/ohm-syscall-probe-' + token
    remote.upload(binary, remote_binary)
    started = time.time_ns()
    code = '''import json,subprocess
def call(args):
 p=subprocess.run(args,capture_output=True,timeout=25)
 return {'returncode':p.returncode,'stdout':p.stdout.decode('ascii'),'stderr':p.stderr.decode('ascii')}
'''
    code += f'upload=call({["hdc", "file", "send", remote_binary, device_binary]!r})\n'
    code += f'permission=call({["hdc", "shell", "chmod 700 " + device_binary]!r})\n'
    code += 'try:\n'
    command = device_binary + (' ' + ' '.join(arguments) if arguments else '')
    code += f' result=call({["hdc", "shell", command]!r})\n'
    code += 'finally:\n'
    code += f' cleanup=call({["hdc", "shell", "rm -f " + device_binary]!r})\n'
    code += "print(json.dumps({'upload':upload,'permission':permission,'run':result,'cleanup':cleanup}))\n"
    transport = json.loads(remote.python(code, timeout=100))
    rows = [json.loads(line) for line in transport['run']['stdout'].splitlines() if line.startswith('{')]
    terminal = [row for row in rows if row.get('kind') == 'calibration']
    passed = (len(terminal) == 1 and terminal[0].get('passed') is True
              and terminal[0].get('returned_bytes') == 31
              and terminal[0].get('writes') == 2
              and terminal[0].get('app_traced') is False
              and all(transport[k]['returncode'] == 0 for k in ('upload', 'permission', 'run', 'cleanup')))
    proof = {'status': 'OWN_CHILD_SYSCALL_CALIBRATION_PASSED' if passed else 'CAPABILITY_NOT_PROVEN',
             'started_unix_ns': started, 'ended_unix_ns': time.time_ns(),
             'source_sha256': hashlib.sha256((ROOT/'tools/native_syscall_probe.c').read_bytes()).hexdigest(),
             'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
             'native_transport': transport, 'events': rows,
             'probe_arguments': list(arguments),
             'app_attached': False, 'app_attach_permission_proven': False,
             'app_write_volume_proven': False, 'performance_accepted': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nr-phase', action='store_true', help='Own-child-only syscall-number phase experiment')
    parser.add_argument('--raw-registers', action='store_true', help='Compare read-only GETREGSET/GETREGS on the own child only')
    args = parser.parse_args()
    if args.nr_phase and args.raw_registers:
        parser.error('select only one own-child calibration mode')
    mode = ('--raw-registers',) if args.raw_registers else ('--nr-phase',) if args.nr_phase else ()
    print(calibrate(Remote(), args.binary, args.output, mode)['status'])
