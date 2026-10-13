#!/usr/bin/env python3
"""Sign rebuilt cases with the existing device-workstation identity and audit them."""
import argparse
import json
import zipfile
from pathlib import Path

from remote_device import Remote

ROOT = Path(__file__).resolve().parents[1]


def sign_case(remote, case, variant, artifacts):
    cid, bundle = case["id"], case["host_app"]["bundle_name"]
    local = artifacts / cid / variant
    build = json.loads((local / "build.json").read_text())
    if build["status"] != "PASS" or not build["source"]["passed"] or not build["hap"]["passed"]:
        raise RuntimeError("unsigned build has not passed clean audit")
    folder = f"/home/research/ohm-clean/{cid}/{variant}"
    record = local / "sign.json"
    with zipfile.ZipFile(local / "app-unsigned.hap") as package:
        requested = {p['name'] for p in json.loads(package.read('module.json'))['module'].get('requestPermissions', [])}
    allowed_acls = sorted(requested & {'ohos.permission.SYSTEM_FLOAT_WINDOW'})
    if record.exists():
        previous = json.loads(record.read_text())
        if previous.get("status") == "PASS" and previous.get("unsigned_sha256") == build["hap"]["sha256"] and previous.get("allowed_acls", []) == allowed_acls:
            remote.python("import hashlib\nfrom pathlib import Path\n"
                          f"assert hashlib.sha256(Path({previous['signed_hap']!r}).read_bytes()).hexdigest()=={previous['audit']['sha256']!r}\n",
                          timeout=300)
            print(f"{cid}/{variant}: verified existing signed artifact", flush=True)
            return
    remote_source = folder + "/app-unsigned.hap"
    remote.upload(local / "app-unsigned.hap", remote_source)
    # Reuse the established signing identity, never generate a replacement or
    # uninstall the app. Audit the signed package before any device installation.
    code = """import hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
os.environ['PATH']='/home/research/.local/bin:'+os.environ['PATH']
sys.path.insert(0,'/home/research/ohm-clean/tools')
from audit_clean_app import audit_hap
"""
    code += f"unsigned=Path({remote_source!r}); signed=unsigned.with_name('app.hap')\n"
    code += f"assert hashlib.sha256(unsigned.read_bytes()).hexdigest()=={build['hap']['sha256']!r}\n"
    code += "spec=importlib.util.spec_from_file_location('signing','/home/research/ohm-clean/tools/sdk_signing.py')\n"
    code += "signing=importlib.util.module_from_spec(spec);spec.loader.exec_module(signing)\n"
    code += f"signing.sign(str(unsigned),str(signed),{bundle!r})\n"
    code += "audit=audit_hap(signed,Path('/home/research/OhmBenchmark-toolchain/command-line-tools/sdk/default/openharmony/toolchains/ark_disasm'))\n"
    code += "assert audit['passed'],audit\n"
    code += f"record={{'case':{cid!r},'variant':{variant!r},'unsigned_sha256':{build['hap']['sha256']!r},'signed_hap':str(signed),'audit':audit,'allowed_acls':{allowed_acls!r},'status':'PASS'}}\n"
    code += "signed.with_name('sign.json').write_text(json.dumps(record,indent=2)+'\\n')\n"
    remote.python(code, timeout=600)
    remote.download(folder + "/sign.json", record)
    print(f"{cid}/{variant}: signed and audited", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--remote", default="cityuPC")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts/clean")
    args = parser.parse_args()
    remote = Remote(args.remote)
    remote.upload(ROOT / "tools/audit_clean_app.py", "/home/research/ohm-clean/tools/audit_clean_app.py")
    remote.upload(ROOT / "tools/sdk_signing.py", "/home/research/ohm-clean/tools/sdk_signing.py")
    for path in sorted((ROOT / "cases").glob("*/case.json")):
        case = json.loads(path.read_text())
        if args.cases and case["id"] not in args.cases:
            continue
        for variant in ("unfixed", "fixed"):
            sign_case(remote, case, variant, args.artifacts)


if __name__ == "__main__":
    main()
