#!/usr/bin/env python3
"""Publish factual clean-build receipts, archiving (not reusing) old perf evidence."""
import json
import subprocess
import hashlib
from pathlib import Path
from clean_sources import app_ref

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
            ref = app_ref(c, variant)
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
                    value = json.loads(receipt.read_text())
                    if receipt_name == 'sign':
                        if value.get('unsigned_sha256') != item['unsigned_sha256']:
                            continue
                    else:
                        current_sign = item.get('sign')
                        if not current_sign or value.get('signed_sha256') != current_sign['audit']['sha256']:
                            continue
                        if receipt_name in ('workload','performance'):
                            plan = path.parent/c['testcase']['workload']
                            if value.get('plan_sha256') != hashlib.sha256(plan.read_bytes()).hexdigest():
                                continue
                    item[receipt_name] = value
            clean["variants"][variant] = item
            rows.append({"case": cid, "variant": variant, "host": host, **item})
        c["build"] = builds
        if all(clean['variants'][v].get('workload',{}).get('status')=='PASS' for v in ('unfixed','fixed')):
            clean['workload_validation']='verified'
        if oracle['evidence'].get('status')=='measured_clean' and all(
                clean['variants'][v].get('performance',{}).get('status')=='PASS' for v in ('unfixed','fixed')):
            clean['performance_validation']='verified'
        if oracle['evidence'].get('status')=='measured_clean_failed' and all(
                clean['variants'][v].get('performance',{}).get('status')=='FAIL' for v in ('unfixed','fixed')):
            clean['performance_validation']='failed'
        if oracle['evidence'].get('status')=='negative_screen_failed' and all(
                clean['variants'][v].get('performance',{}).get('status')=='NEGATIVE_SCREEN_FAILED' for v in ('unfixed','fixed')):
            clean['performance_validation']='negative_screen_failed'
        if oracle['evidence'].get('status')=='primary_criterion_met_mechanism_screen_failed' and all(
                clean['variants'][v].get('performance',{}).get('status')=='MECHANISM_SCREEN_FAILED' for v in ('unfixed','fixed')):
            clean['performance_validation']='mechanism_screen_failed'
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
    contracts={}
    for path in sorted((ROOT/'cases').glob('*/case.json')):
        case=json.loads(path.read_text())
        measured=case['clean_validation']['performance_validation']=='verified'
        failed=case['clean_validation']['performance_validation']=='failed'
        screened=case['clean_validation']['performance_validation']=='negative_screen_failed'
        mechanism_screened=case['clean_validation']['performance_validation']=='mechanism_screen_failed'
        contracts[case['id']]={'oracle_metric':case['test_oracle']['metric'],'app_injection':False,
            'workload_validation':case['clean_validation']['workload_validation'],
            'measurement_status':'measured_clean' if measured else 'measured_clean_failed' if failed else 'negative_screen_failed' if screened else 'primary_criterion_met_mechanism_screen_failed' if mechanism_screened else 'pending_clean_measurement',
            'rounds_recorded':case['test_oracle']['evidence'].get('rounds_per_variant',0) if measured or failed or screened or mechanism_screened else 0}
        if mechanism_screened:
            contracts[case['id']].update(primary_criterion_met=True,mechanism_criterion_met=False,full_case_accepted=False)
        if case.get('disposition'):
            contracts[case['id']]['disposition'] = case['disposition']
    (ROOT/'cases/measurement-contract.json').write_text(json.dumps({
        '$comment':'External clean measurement contract. Historical instrumented evidence is archived and not reused.',
        'case_count':len(contracts),'measured_case_count':sum(c['measurement_status']=='measured_clean' for c in contracts.values()),
        'skipped_case_count':sum(c.get('disposition',{}).get('status')=='skipped_by_user' for c in contracts.values()),
        'cases':contracts},indent=2)+'\n')
    print(f"{len(rows)}/60 clean build receipts published; old performance evidence archived")


if __name__ == "__main__":
    main()
