"""Private bounded native HiLog stream, external to the observed application."""
import hashlib
from pathlib import Path
import re
import subprocess
import time

from system_pss import start_ticks


def logger_command(raw, app_pid):
    # This device exposes only "hilog" in /proc/PID/cmdline, not argv. The
    # wrapper's selection+pre-exec stat markers bind the target and lifetime.
    words = raw.rstrip('\0').split('\0')
    if len(words) == 1:
        words = words[0].split()
    return bool(words and Path(words[0]).name == 'hilog' and
                (len(words) == 1 or words[1:3] == ['-P', str(app_pid)]))


class NativeHiLogStream:
    def __init__(self, shell, app_pid, binary, directory, duration=180):
        if type(app_pid) is not int or app_pid <= 0 or type(duration) is not int or not 1 <= duration <= 180:
            raise ValueError('invalid native log stream target/lifetime')
        if not re.fullmatch(r'/data/local/tmp/[A-Za-z0-9_-]+', binary):
            raise ValueError('use the explicitly deployed external logger')
        self.shell, self.app_pid, self.binary = shell, app_pid, binary
        self.directory, self.duration = Path(directory), duration
        self.reader = None
        self.owner = None
        self.handles = []
        self.closed_successfully = False

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.started = time.monotonic()
        self.app_stat = self.shell(f'cat /proc/{self.app_pid}/stat')
        for stream in ('stdout', 'stderr'):
            path = self.directory/(stream+'.bin')
            handle = path.open('xb')
            path.chmod(0o600)
            self.handles.append(handle)
        self.reader = subprocess.Popen(['hdc', 'shell', f'{self.binary} {self.app_pid} {self.duration}'],
                                       stdout=self.handles[0], stderr=self.handles[1])
        try:
            deadline = time.monotonic()+10
            while time.monotonic() < deadline:
                raw = (self.directory/'stdout.bin').read_bytes()
                match = re.search(rb'^__OHM_HILOG_OWNER__(\d+)\r?\n', raw, re.M)
                selection = re.search(rb'^__OHM_HILOG_SELECTION__(\d+) (\d+)\r?\n', raw, re.M)
                launch = re.search(rb'^__OHM_HILOG_STAT__([^\n]+)\n', raw, re.M)
                if match and selection and launch:
                    pid = int(match[1])
                    if (int(selection[1]), int(selection[2])) != (self.app_pid, self.duration):
                        raise RuntimeError('native logger selected a different target/lifetime')
                    launch_stat = launch[1].decode('ascii')
                    stat = self.shell(f'cat /proc/{pid}/stat')
                    if start_ticks(stat, pid) != start_ticks(launch_stat, pid):
                        raise RuntimeError('native logger PID changed before readiness')
                    if logger_command(self.shell(f'cat /proc/{pid}/cmdline'), self.app_pid):
                        self.owner = {'pid': pid, 'stat': stat, 'start_ticks': start_ticks(stat, pid),
                                      'launch_stat': launch_stat, 'selected_app_pid': self.app_pid,
                                      'selected_lifetime_s': self.duration}
                        self.ready = time.monotonic()
                        return self
                if self.reader.poll() is not None:
                    raise RuntimeError('native logger exited before readiness')
                time.sleep(.05)
            raise RuntimeError('native logger ownership/readiness not proven')
        except Exception:
            self.close()
            raise

    def close(self):
        if self.closed_successfully:
            return
        unexpected_exit = self.reader is not None and self.reader.poll() is not None and self.owner is not None
        if self.owner:
            pid = self.owner['pid']
            stat = self.shell(f'cat /proc/{pid}/stat 2>/dev/null || true')
            if stat.startswith(str(pid)+' (') and start_ticks(stat, pid) == self.owner['start_ticks']:
                if not logger_command(self.shell(f'cat /proc/{pid}/cmdline'), self.app_pid):
                    raise RuntimeError('owned native logger changed command; do not signal it')
                self.shell(f'kill -TERM {pid}')
        if self.reader:
            try:
                self.reader.wait(timeout=10 if self.owner else self.duration+5)
            except subprocess.TimeoutExpired:
                self.reader.terminate()
                self.reader.wait(timeout=5)
        for handle in self.handles:
            handle.close()
        self.ended = time.monotonic()
        if self.owner:
            pid = self.owner['pid']
            stat = self.shell(f'cat /proc/{pid}/stat 2>/dev/null || true')
            if stat.startswith(str(pid)+' (') and start_ticks(stat, pid) == self.owner['start_ticks']:
                raise RuntimeError('owned native logger remains live; inspect before any new task')
        if self.reader and self.owner:
            if start_ticks(self.shell(f'cat /proc/{self.app_pid}/stat'), self.app_pid) != start_ticks(self.app_stat, self.app_pid):
                raise RuntimeError('observed app process changed during native logging')
        if unexpected_exit:
            raise RuntimeError('native logger exited before the observed workload finished')
        self.closed_successfully = True

    def __exit__(self, kind, value, trace):
        self.close()

    def receipt(self):
        if not self.closed_successfully or self.owner is None:
            raise RuntimeError('native stream cleanup/ownership is not fully verified')
        result = {'app_pid': self.app_pid, 'app_stat': self.app_stat, 'logger_owner': self.owner,
                  'started_monotonic': self.started, 'ready_monotonic': self.ready,
                  'ended_monotonic': self.ended, 'hard_lifetime_s': self.duration,
                  'logger_owner_gone': True, 'app_injection': False}
        for stream in ('stdout', 'stderr'):
            raw = (self.directory/(stream+'.bin')).read_bytes()
            result[stream+'_sha256'] = hashlib.sha256(raw).hexdigest()
            result[stream+'_bytes'] = len(raw)
        return result
