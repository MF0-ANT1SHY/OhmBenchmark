"""Retain exact existing native HiLog bytes, including truncated UTF-8 records.

Only the evaluator uses replacement decoding for inspecting log lines. The raw
stream and its hash remain available; no app source or log emission is changed.
"""
import hashlib
from pathlib import Path
import re
import subprocess
import time


def snapshot(pid, directory, label):
    if (type(pid) is not int or pid <= 0 or not isinstance(label,str) or
            not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',label)):
        raise ValueError('invalid native HiLog snapshot identity')
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True,mode=0o700);directory.chmod(0o700)
    out=directory/(label+'.stdout.bin');err=directory/(label+'.stderr.bin')
    if out.exists() or err.exists():
        raise FileExistsError('preserve existing native HiLog snapshots')
    started=time.monotonic()
    result=subprocess.run(['hdc','shell',f'hilog -x -P {pid} -v epoch -v nsec'],capture_output=True,timeout=90)
    ended=time.monotonic()
    for path,blob in ((out,result.stdout),(err,result.stderr)):
        path.write_bytes(blob);path.chmod(0o600)
    if result.returncode:
        raise RuntimeError('native HiLog command failed; raw streams preserved in '+str(directory))
    try:
        text=result.stdout.decode('utf-8');strict=True
    except UnicodeDecodeError:
        text=result.stdout.decode('utf-8',errors='replace');strict=False
    return {'pid':pid,'raw_logs':text,'raw_file':str(out),'raw_sha256':hashlib.sha256(result.stdout).hexdigest(),
            'raw_bytes':len(result.stdout),'stderr_file':str(err),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest(),
            'started_monotonic':started,'ended_monotonic':ended,
            'strict_utf8':strict,'replacement_decoding_used':not strict,
            'method':'existing native HiLog bytes; no app instrumentation'}
