#!/usr/bin/env python3
"""Install each audited clean HAP and verify launch; this is NOT a perf verdict."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from remote_device import Remote

ROOT = Path(__file__).resolve().parents[1]


def smoke(remote, case, variant, artifacts):
    folder = artifacts / case["id"] / variant
    signed = json.loads((folder / "sign.json").read_text())
    if signed["status"] != "PASS" or not signed["audit"]["passed"]:
        raise RuntimeError("signed artifact has not passed audit")
    code = "import hashlib\nfrom pathlib import Path\n"
    code += f"assert hashlib.sha256(Path({signed['signed_hap']!r}).read_bytes()).hexdigest()=={signed['audit']['sha256']!r}\n"
    remote.python(code, timeout=300)
    previous_path = folder / "smoke.json"
    if previous_path.exists():
        previous = json.loads(previous_path.read_text())
        if previous.get("status") == "PASS" and previous.get("signed_sha256") == signed["audit"]["sha256"]:
            print(f"{case['id']}/{variant}: verified recorded smoke evidence for identical signed artifact", flush=True)
            return
    bundle = case["host_app"]["bundle_name"]
    ability = case["testcase"]["ability"]
    remote.hdc(["shell", f"aa force-stop {bundle}"])
    install = remote.hdc(["install", "-r", signed["signed_hap"]], timeout=180)
    if "install bundle successfully" not in install:
        raise RuntimeError(f"installation failed (no uninstall attempted): {install}")
    # Remove only historical measurement outputs, after backing them up. Business
    # data is left intact; reproducible fixture preparation is a separate step.
    module = case["testcase"]["module"]
    files = f"/data/app/el2/100/base/{bundle}/haps/{module}/files"
    remote.python("from pathlib import Path\nimport subprocess\n"
                  f"dest=Path('/home/research/ohm-clean/backups/{bundle}/legacy-probes');dest.mkdir(parents=True,exist_ok=True)\n"
                  f"base={files!r}\n"
                  "for name in ['ohm-status.json','ohm-diag.json','ohm-go']:\n"
                  " p=base+'/'+name\n"
                  " exists=subprocess.run(['hdc','shell','test -f '+p+' && echo present'],capture_output=True,text=True).stdout\n"
                  " if 'present' in exists:\n"
                  "  subprocess.run(['hdc','file','recv',p,str(dest/name)],check=True,capture_output=True)\n"
                  "  subprocess.run(['hdc','shell','rm -f '+p],check=True,capture_output=True)\n")
    launch = remote.hdc(["shell", f"aa start -a {ability} -b {bundle}"])
    if "start ability successfully" not in launch:
        raise RuntimeError(f"launch failed: {launch}")
    time.sleep(2)
    pids = remote.hdc(["shell", f"pidof {bundle}"]).strip()
    if not re.fullmatch(r"\d+(?:\s+\d+)*", pids):
        raise RuntimeError(f"application is not alive after launch: {pids!r}")
    layout_path = "/data/local/tmp/clean-smoke-layout.json"
    remote.hdc(["shell", f"uitest dumpLayout -p {layout_path}"])
    layout = json.loads(remote.hdc(["shell", f"cat {layout_path}"]))
    def bundles(node):
        yield node.get("attributes", {}).get("bundleName")
        for child in node.get("children", []):
            yield from bundles(child)
    if bundle not in set(bundles(layout)):
        raise RuntimeError("launched app has no visible foreground UI")
    (folder / "smoke-layout.json").write_text(json.dumps(layout, ensure_ascii=False))
    record = {"case": case["id"], "variant": variant, "signed_sha256": signed["audit"]["sha256"],
              "install": install.strip(), "launch": launch.strip(), "pids": list(map(int,pids.split())),
              "foreground_bundle": bundle, "status": "PASS", "performance_verified": False}
    (folder / "smoke.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"{case['id']}/{variant}: installed, running, foreground UI verified", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--remote", default="cityuPC")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts/clean")
    args = parser.parse_args()
    remote = Remote(args.remote)
    for path in sorted((ROOT / "cases").glob("*/case.json")):
        case = json.loads(path.read_text())
        if args.cases and case["id"] not in args.cases:
            continue
        for variant in ("unfixed", "fixed"):
            smoke(remote, case, variant, args.artifacts)


if __name__ == "__main__":
    main()
