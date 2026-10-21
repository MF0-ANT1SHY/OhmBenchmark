#!/usr/bin/env python3
"""Transport artifacts/commands to a WSL or native Windows workstation via SSH.

No keys or account passwords are copied. Signing uses the identity already on
that workstation. The installed application's bundle name is not rewritten.
"""
import argparse
import base64
import hashlib
import re
import subprocess
from pathlib import Path


class Remote:
    def __init__(self, host="cityuPC", distro="Ubuntu-24.04", backend=None):
        self.host, self.distro = host, distro
        self.backend = backend or ('windows' if host.lower() in
                                   ('hkrc', 'hkrc-2', 'hkrc_2', 'hkrc_2-laptop') else 'wsl')
        if self.backend not in ('wsl', 'windows'):
            raise ValueError('remote backend must be wsl or windows')

    def python(self, code, data=None, timeout=120):
        # Windows OpenSSH uses cmd.exe, whose quoting differs from POSIX. Keep
        # arbitrary source out of its command line: fixed bash -s entry, stdin script.
        script = "python3 - <<'OHM_REMOTE_PY'\n" + code + "\nOHM_REMOTE_PY\n"
        if data is not None:
            # File payloads are embedded in a Python string, not shell commands.
            script = "python3 - <<'OHM_REMOTE_PY'\nPAYLOAD = " + repr(data) + "\n" + code + "\nOHM_REMOTE_PY\n"
        command = f"wsl -d {self.distro} -- bash -s"
        if self.backend == 'windows':
            # Feed Python directly. Windows cmd.exe never parses source or data.
            script = ("PAYLOAD = " + repr(data) + "\n" if data is not None else "") + code
            command = 'python -X utf8 -'
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, command],
                                input=script.encode(), capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"))
        return result.stdout.decode(errors="replace")

    def upload(self, source, destination):
        blob = source.read_bytes()
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(destination)):
            raise ValueError("remote transfer path must be absolute and contain no shell metacharacters")
        digest = hashlib.sha256(blob).hexdigest()
        # Stream binary data directly, avoiding a 500MB Python heredoc for the
        # music app's bundled audio. cmd.exe sees only fixed code and validated args.
        code = ("import sys,hashlib; from pathlib import Path; "
                "blob=sys.stdin.buffer.read(); digest=hashlib.sha256(blob).hexdigest(); "
                "assert digest==sys.argv[2]; p=Path(sys.argv[1]); "
                "p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(blob); print(digest)")
        interpreter = ('python -X utf8' if self.backend == 'windows'
                       else f'wsl -d {self.distro} -- python3')
        command = f'{interpreter} -c "{code}" {destination} {digest}'
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, command],
                                input=blob, capture_output=True, timeout=600)
        if result.returncode or result.stdout.decode(errors="replace").strip() != digest:
            raise RuntimeError("remote binary transfer failed integrity verification: " +
                               result.stderr.decode(errors="replace"))
        return str(destination)

    def download(self, source, destination):
        code = ("import base64\nfrom pathlib import Path\n"
                f"print(base64.b64encode(Path({str(source)!r}).read_bytes()).decode())")
        blob = base64.b64decode(self.python(code, timeout=300).strip(), validate=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(blob)

    def hdc(self, args, timeout=90):
        code = "import subprocess\n" + f"args={list(args)!r}\n"
        if self.backend == 'windows':
            # HDC resolves slash-rooted host paths against cwd rather than the
            # drive root. Python's absolute Windows paths avoid that ambiguity.
            code += "from pathlib import Path\n"
            code += "if args and args[0]=='install':\n"
            code += " args=[str(Path(a).resolve()) if a.startswith('/') else a for a in args]\n"
            code += "if args[:2]==['file','send']:args[2]=str(Path(args[2]).resolve())\n"
            code += "if args[:2]==['file','recv']:args[3]=str(Path(args[3]).resolve())\n"
        return self.python(code +
                           f"p=subprocess.run(['hdc',*args],capture_output=True,text=True,timeout={timeout})\n"
                           "print(p.stdout,end='');print(p.stderr,end='')\n"
                           "raise SystemExit(p.returncode)", timeout=timeout+20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="cityuPC")
    sub = parser.add_subparsers(dest="operation", required=True)
    upload = sub.add_parser("upload")
    upload.add_argument("source", type=Path)
    upload.add_argument("destination")
    download = sub.add_parser("download")
    download.add_argument("source")
    download.add_argument("destination", type=Path)
    hdc = sub.add_parser("hdc")
    hdc.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    remote = Remote(args.host)
    if args.operation == "upload":
        print(remote.upload(args.source, args.destination))
    elif args.operation == "download":
        remote.download(args.source, args.destination)
    else:
        print(remote.hdc(args.args))


if __name__ == "__main__":
    main()
