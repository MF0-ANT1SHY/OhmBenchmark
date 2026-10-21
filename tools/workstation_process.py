"""Read a host process identity; never signal or replace the process."""
import json
import os
from pathlib import Path
import subprocess


def identity(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('positive process ID required')
    if os.name != 'nt':
        proc = Path('/proc') / str(pid)
        return {'start_ticks': int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]),
                'command': (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode()}
    # Only the validated integer enters PowerShell source.
    code = (f'$p=Get-CimInstance Win32_Process -Filter "ProcessId={pid}"; '
            'if ($null -eq $p) { exit 2 }; '
            '@{start_ticks=$p.CreationDate.ToUniversalTime().Ticks; command=$p.CommandLine} | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', code],
                            check=True, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout)
