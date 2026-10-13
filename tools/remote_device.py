#!/usr/bin/env python3
"""Transport artifacts/commands to the existing WSL device workstation via SSH.

No keys or account passwords are copied. Signing uses the identity already on
that workstation. The installed application's bundle name is not rewritten.
"""
import argparse
import base64
import hashlib
import subprocess
from pathlib import Path


class Remote:
    def __init__(self, host="cityuPC", distro="Ubuntu-24.04"):
        self.host, self.distro = host, distro

    def python(self, code, data=None, timeout=120):
        # Windows OpenSSH uses cmd.exe, whose quoting differs from POSIX. Keep
        # arbitrary source out of its command line: fixed bash -s entry, stdin script.
        script = "python3 - <<'OHM_REMOTE_PY'\n" + code + "\nOHM_REMOTE_PY\n"
        if data is not None:
            # File payloads are embedded in a Python string, not shell commands.
            script = "python3 - <<'OHM_REMOTE_PY'\nPAYLOAD = " + repr(data) + "\n" + code + "\nOHM_REMOTE_PY\n"
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host,
                                 f"wsl -d {self.distro} -- bash -s"],
                                input=script.encode(), capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"))
        return result.stdout.decode(errors="replace")

    def upload(self, source, destination):
        blob = source.read_bytes()
        code = ("import base64,hashlib\nfrom pathlib import Path\n"
                f"p=Path({str(destination)!r});p.parent.mkdir(parents=True,exist_ok=True)\n"
                "blob=base64.b64decode(PAYLOAD)\n"
                f"assert hashlib.sha256(blob).hexdigest()=={hashlib.sha256(blob).hexdigest()!r}\n"
                "p.write_bytes(blob)\nprint(str(p))")
        return self.python(code, base64.b64encode(blob).decode(), timeout=300)

    def download(self, source, destination):
        code = ("import base64\nfrom pathlib import Path\n"
                f"print(base64.b64encode(Path({str(source)!r}).read_bytes()).decode())")
        blob = base64.b64decode(self.python(code, timeout=300).strip(), validate=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(blob)

    def hdc(self, args, timeout=90):
        return self.python("import subprocess\n"
                           f"p=subprocess.run({['hdc', *args]!r},capture_output=True,text=True,timeout={timeout})\n"
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
