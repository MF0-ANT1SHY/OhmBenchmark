#!/usr/bin/env python3
"""Verify clean builds independently from signed/smoke/workload/performance gates."""
import argparse
import ast
import json
import subprocess
from pathlib import Path

from audit_clean_app import audit_hap, audit_source
from clean_sources import app_ref
from accept_cpu_evidence import accept as validate_cpu
from accept_pss_evidence import accept as validate_pss
from accept_trace_evidence import accept as validate_trace
from accept_reader_startup_evidence import accept as validate_startup
from accept_weather_icon_evidence import accept as validate_icons
from accept_ytsearch_payload import accept as validate_search_payload

ROOT = Path(__file__).resolve().parents[1]


def verify(stage, selected=None):
    recon = json.loads((ROOT / "hosts_patches/host-reconstruction.json").read_text())["hosts"]
    paths = sorted((ROOT / "cases").glob("*/case.json"))
    errors, pending = [], []
    if len(paths) != 30:
        errors.append(f"expected 30 cases, found {len(paths)}")
    if selected:
        unknown=set(selected)-{p.parent.name for p in paths}
        if unknown:
            errors.append(f'unknown cases: {sorted(unknown)}')
        paths=[p for p in paths if p.parent.name in selected]
    for path in paths:
        c = json.loads(path.read_text())
        cid = c["id"]
        host = c["host_app"]["local_path"].split("/")[-1]
        repo = ROOT / c["host_app"]["local_path"]
        tc = c["testcase"]
        source = (path.parent / tc["py_file"]).read_text()
        ast.parse(source)
        if any(term in source for term in ("run_bench", "wait_state", "ohm-go", "--ps bench", "CASE_ID")):
            errors.append(f"{cid}: retired app-side protocol or identity in testcase")
        plan = json.loads((path.parent / tc["workload"]).read_text())
        if not plan.get("measured") or any(phase not in plan for phase in ("setup", "measured", "verify")):
            errors.append(f"{cid}: incomplete external workload plan")
        if plan["bundle"] != c["host_app"]["bundle_name"] or plan["ability"] != tc["ability"]:
            errors.append(f"{cid}: workload targets wrong app")
        diff = subprocess.check_output(["git", "-C", str(repo), "diff",
                                      app_ref(c,'unfixed'), app_ref(c,'fixed')])
        if diff != (path.parent / "fix.patch").read_bytes():
            errors.append(f"{cid}: repair diff does not match clean app trees")
        for variant in ("unfixed", "fixed"):
            label = f"{cid}/{variant}"
            entry = recon[host]["case_tags"][f"case/{cid}/{variant}"]
            ref = app_ref(c, variant)
            audit = audit_source(repo, ref)
            expected = entry.get("app_tree", entry["tree"])
            folder = ROOT / "artifacts/clean" / cid / variant
            build = json.loads((folder / "build.json").read_text())
            if audit["tree"] != expected or not audit["passed"] or build["source"]["tree"] != expected:
                errors.append(f"{label}: source provenance/audit failed")
            hap = audit_hap(folder / "app-unsigned.hap", ROOT / "toolchain/command-line-tools/sdk/default/openharmony/toolchains/ark_disasm")
            if not hap["passed"] or hap["sha256"] != build["hap"]["sha256"] or build["status"] != "PASS":
                errors.append(f"{label}: artifact audit/build failed")
            required = [] if stage == "build" else ["sign"]
            if stage in ("smoke", "complete"):
                required += ["smoke"]
            if stage == "complete":
                required += ["workload", "performance"]
            for kind in required:
                receipt = folder / f"{kind}.json"
                if not receipt.exists():
                    pending.append(f"{label}: {kind} evidence missing")
                    continue
                r = json.loads(receipt.read_text())
                if r.get("status") != "PASS":
                    pending.append(f"{label}: {kind} not validated")
                if kind == "sign" and r.get("unsigned_sha256") != hap["sha256"]:
                    errors.append(f"{label}: signature receipt belongs to another build")
                if kind in ("smoke", "workload", "performance"):
                    signed = json.loads((folder / "sign.json").read_text())
                    if r.get("signed_sha256") != signed["audit"]["sha256"]:
                        errors.append(f"{label}: {kind} receipt belongs to another signed artifact")
                if kind == "performance" and (r.get("rounds", 0) < 3 or r.get("metric") != c["test_oracle"]["metric"]):
                    errors.append(f"{label}: oracle coverage/rounds not proven")
        evidence_status=c['test_oracle']['evidence'].get('status')
        if stage=='complete' and evidence_status!='measured_clean':
            pending.append(f'{cid}: clean performance oracle not accepted ({evidence_status})')
        if stage == 'complete' and c['test_oracle']['evidence'].get('status')=='measured_clean':
            if c['test_oracle']['metric'] in ('hiperf_instructions','app_pss_bytes','startup_icons_elapsed_s','search_response_body_bytes') or cid in ('sheafreader_refresh_feeds_sequential', 'sheafreader_unread_counts_n_plus_1', 'wanharmony_history_log_materialization'):
                try:
                    validator={'hiperf_instructions':validate_cpu,'app_pss_bytes':validate_pss,'trace_cpu_ms':validate_trace, 'startup_refresh_elapsed_s':validate_startup, 'startup_icons_elapsed_s':validate_icons, 'search_response_body_bytes':validate_search_payload}[c['test_oracle']['metric']]
                    recomputed=validator(cid,write=False)
                    for variant,expected in recomputed.items():
                        actual=json.loads((ROOT/'artifacts/clean'/cid/variant/'performance.json').read_text())
                        if actual!=expected:
                            errors.append(f'{cid}/{variant}: performance receipt differs from raw evidence')
                    evidence=c['test_oracle']['evidence']
                    if any(evidence.get(v)!=recomputed[v]['samples'] for v in ('unfixed','fixed')):
                        errors.append(f'{cid}: case evidence differs from raw measurements')
                except Exception as exc:
                    errors.append(f'{cid}: raw {c["test_oracle"]["metric"]} evidence failed: {exc}')
            else:
                pending.append(f'{cid}: raw oracle verification is not implemented for this metric')
    print(json.dumps({"stage": stage, "cases": len(paths), "errors": errors,
                      "pending": pending, "passed": not errors and not pending}, indent=2))
    return int(bool(errors or pending))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["build", "sign", "smoke", "complete"], default="complete")
    parser.add_argument('--case', action='append', dest='cases', help='verify this case (repeatable), retaining the 30-case inventory check')
    args = parser.parse_args()
    raise SystemExit(verify(args.stage,args.cases))
