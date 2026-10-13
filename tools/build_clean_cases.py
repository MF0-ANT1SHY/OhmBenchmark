#!/usr/bin/env python3
"""Build all 60 business-only HAPs in new worktrees; audit compiled artifacts."""
import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from audit_clean_app import audit_hap, audit_source

ROOT = Path(__file__).resolve().parents[1]


def build_case(case, variant, output, toolchain, mode):
    cid = case["id"]
    repo = ROOT / case["host_app"]["local_path"]
    ref = f"clean-app/{cid}/{variant}"
    dest = output / cid / variant
    dest.mkdir(parents=True, exist_ok=True)
    source = audit_source(repo, ref)
    if not source["passed"]:
        raise RuntimeError(f"injected source: {source['findings']}")
    receipt = dest / "build.json"
    if receipt.exists():
        old = json.loads(receipt.read_text())
        if old.get("status") == "PASS" and old.get("source", {}).get("tree") == source["tree"] and old.get("mode") == mode:
            audit = audit_hap(dest / "app-unsigned.hap", toolchain / "sdk/default/openharmony/toolchains/ark_disasm")
            if audit["passed"] and audit["sha256"] == old["hap"]["sha256"]:
                print(f"{cid}/{variant}: verified existing clean build", flush=True)
                return old
    wt = output / "worktrees" / cid / variant
    if wt.exists():
        actual = subprocess.check_output(["git", "-C", str(wt), "rev-parse", "HEAD^{tree}"], text=True).strip()
        if not receipt.exists() or actual != source["tree"]:
            raise RuntimeError(f"unrecognized unfinished worktree: {wt}")
    else:
        wt.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), ref], check=True, capture_output=True)
    env = os.environ.copy()
    env["DEVECO_SDK_HOME"] = str(toolchain / "sdk")
    env["PATH"] = str(toolchain / "bin") + os.pathsep + env["PATH"]
    started = time.time()
    result = {"case": cid, "variant": variant, "ref": ref, "mode": mode, "source": source,
              "status": "FAIL", "toolchain": str(toolchain)}
    try:
        with (dest / "build.log").open("w") as log:
            subprocess.run([str(toolchain / "bin/ohpm"), "install"], cwd=wt, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
            # Package-manager updates may not silently change the claimed source tree.
            dirty_names = subprocess.check_output(["git", "-C", str(wt), "diff", "--name-only"], text=True).splitlines()
            for name in dirty_names:
                if not name.endswith("oh-package-lock.json5"):
                    continue
                original = subprocess.check_output(["git", "-C", str(wt), "show", f"HEAD:{name}"])
                installed = (wt / name).read_bytes()
                # ohpm 5.1.3 adds a formatting-only metadata flag to old locks.
                # Restore it only if this is the ENTIRE difference, not a dependency update.
                normalized = installed.replace(b'"stableOrder": true,\n    "enableUnifiedLockfile": false', b'"stableOrder": true')
                if normalized == original:
                    (wt / name).write_bytes(original)
                    result.setdefault("package_manager_metadata_restored", []).append(name)
            dirty = subprocess.check_output(["git", "-C", str(wt), "diff", "--name-only"], text=True).strip()
            if dirty:
                raise RuntimeError(f"dependency install changed tracked source: {dirty}")
            subprocess.run([str(toolchain / "bin/hvigorw"), "--mode", "module", "-p", "product=default",
                            "-p", f"buildMode={mode}", "assembleHap", "--no-daemon"],
                           cwd=wt, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        artifacts = list(wt.glob("*/build/default/outputs/default/*-unsigned.hap"))
        if len(artifacts) != 1:
            raise RuntimeError(f"expected one unsigned HAP, got {artifacts}")
        target = dest / "app-unsigned.hap"
        shutil.copyfile(artifacts[0], target)
        result["hap"] = audit_hap(target, toolchain / "sdk/default/openharmony/toolchains/ark_disasm")
        if not result["hap"]["passed"]:
            raise RuntimeError(f"injected HAP: {result['hap']['findings']}")
        result["status"] = "PASS"
    except Exception as exc:
        result["error"] = str(exc)
    result["elapsed_s"] = round(time.time() - started, 2)
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{cid}/{variant}: {result['status']} ({result['elapsed_s']}s) {result.get('error', '')}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/clean")
    parser.add_argument("--toolchain", type=Path, default=ROOT / "toolchain/command-line-tools")
    parser.add_argument("--mode", choices=["debug", "release"], default="release")
    args = parser.parse_args()
    output, toolchain = args.output.resolve(), args.toolchain.resolve()
    failed = False
    for path in sorted((ROOT / "cases").glob("*/case.json")):
        case = json.loads(path.read_text())
        if args.cases and case["id"] not in args.cases:
            continue
        for variant in ("unfixed", "fixed"):
            try:
                result = build_case(case, variant, output, toolchain, args.mode)
                failed |= result["status"] != "PASS"
            except Exception as exc:
                print(f"{case['id']}/{variant}: {exc}", flush=True)
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
