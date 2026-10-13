#!/usr/bin/env python3
"""Publish factual clean-build receipts, archiving (not reusing) old perf evidence."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    reconstruction = json.loads((ROOT / "hosts_patches/host-reconstruction.json").read_text())["hosts"]
    rows = []
    for path in sorted((ROOT / "cases").glob("*/case.json")):
        c = json.loads(path.read_text())
        cid = c["id"]
        host = c["host_app"]["local_path"].split("/")[-1]
        repo = ROOT / c["host_app"]["local_path"]
        c.setdefault("legacy_source", {"unfixed_commit": c["unfixed_commit"],
                                        "fixed_commit": c["fixed_commit"], "build": c["build"]})
        oracle = c["test_oracle"]
        if "legacy_instrumented_evidence" not in oracle:
            oracle["legacy_instrumented_evidence"] = oracle["evidence"]
            oracle["evidence"] = {"status": "pending_clean_measurement",
                                  "note": "Legacy instrumented measurements do not validate these business-only builds."}
        c["testcase"]["trigger"] = "external_ui"
        c["testcase"]["workload"] = f"testcase/{c['testcase']['name']}.workload.json"
        clean = {"policy": "no_app_injection", "workload_validation": "pending",
                 "performance_validation": "pending", "variants": {}}
        builds = {"mode": "release"}
        for variant in ("unfixed", "fixed"):
            ref = f"clean-app/{cid}/{variant}"
            entry = reconstruction[host]["case_tags"][f"case/{cid}/{variant}"]
            tree = entry.get("app_tree", entry["tree"])
            commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", ref], text=True).strip()
            c[f"{variant}_commit"] = commit
            item = {"ref": ref, "commit": commit, "tree": tree,
                    "business_base_tree": entry["tree"], "production_patches": entry.get("production_patches", [])}
            folder = ROOT / "artifacts/clean" / cid / variant
            build = json.loads((folder / "build.json").read_text())
            if build["status"] != "PASS" or build["source"]["tree"] != tree or not build["hap"]["passed"]:
                raise RuntimeError(f"{cid}/{variant}: clean build not proven")
            item["unsigned_sha256"] = build["hap"]["sha256"]
            item["bytecode_audit"] = build["hap"]
            item["build_status"] = build["status"]
            builds[f"build_{variant}"] = build["status"]
            for receipt_name in ("sign", "smoke", "workload", "performance"):
                receipt = folder / (receipt_name + ".json")
                if receipt.exists():
                    item[receipt_name] = json.loads(receipt.read_text())
            clean["variants"][variant] = item
            rows.append({"case": cid, "variant": variant, "host": host, **item})
        c["build"] = builds
        c["clean_validation"] = clean
        c["reproduction"] = [
            "python3 tools/reconstruct_clean_hosts.py",
            f"python3 tools/build_clean_cases.py {cid}",
            f"python3 tools/sign_clean_cases.py {cid}",
            "Prepare the external workload fixtures; never apply measurement patches to the app.",
            f"Copy all files from cases/{cid}/testcase/ into {c['testcase']['install_dir']}/.",
            f"Install each clean signed variant and run the {c['testcase']['name']} HapRay testcase for >= 3 rounds.",
            "Verify the real UI path and compare the declared CPU/memory metric; build/smoke success alone is not a performance verdict.",
        ]
        path.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n")
    destination = ROOT / "validation"
    destination.mkdir(exist_ok=True)
    (destination / "clean-builds.json").write_text(json.dumps({"case_count": 30, "variant_count": len(rows),
        "performance_evidence_reused": False, "variants": rows}, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(rows)}/60 clean build receipts published; old performance evidence archived")


if __name__ == "__main__":
    main()
