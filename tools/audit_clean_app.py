#!/usr/bin/env python3
"""Reject benchmark injection in source trees and disassembled HAP bytecode."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

# Original business counters/logging are allowed. These are measurement-only names
# and protocols, not a ban on the app legitimately using indexOf/JSON.parse/etc.
INJECTION = re.compile(
    r"(?i)ohm(?:probe|counters?|diag|scan|decode|persist|progresslog|font|row|update|play|concat|log|ctr)"
    r"|ohm[-_](?:status|diag|go)|OHMB/|OHM_[A-Z_]+"
    r"|(?:Browser|Cloud|Interview|Jingmo|SheafUi|Sheaf|Weather|YtMusic)Bench"
    r"|want\.parameters(?:\?\.)?(?:\[['\"]bench['\"]\]|\.bench)"
)


def findings(text):
    return [{"line": i, "token": m.group()} for i, line in enumerate(text.splitlines(), 1)
            for m in INJECTION.finditer(line)]


def audit_source(repo, ref):
    tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", f"{ref}^{{tree}}"], text=True).strip()
    names = subprocess.check_output(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref], text=True).splitlines()
    hits = []
    for name in names:
        if Path(name).suffix not in {".ets", ".ts", ".js", ".json", ".json5", ".cpp", ".h"}:
            continue
        content = subprocess.check_output(["git", "-C", str(repo), "show", f"{ref}:{name}"]).decode(errors="replace")
        hits.extend({"file": name, **hit} for hit in findings(content))
    return {"tree": tree, "files_checked": len(names), "findings": hits, "passed": not hits}


def audit_hap(hap, disassembler):
    hits, checked = [], []
    with tempfile.TemporaryDirectory(prefix="ohm-audit-") as tmp:
        with zipfile.ZipFile(hap) as package:
            for name in package.namelist():
                hits.extend({"file": name, **hit} for hit in findings(name))
                if name.endswith(".abc"):
                    abc = Path(tmp) / (str(len(checked)) + ".abc")
                    output = abc.with_suffix(".pa")
                    abc.write_bytes(package.read(name))
                    subprocess.run([str(disassembler), str(abc), str(output)], check=True,
                                   capture_output=True, timeout=120)
                    text = output.read_text(errors="replace")
                    if not text.strip():
                        raise RuntimeError(f"empty bytecode disassembly: {name}")
                    checked.append(name)
                    hits.extend({"file": name, **hit} for hit in findings(text))
                elif name.endswith((".json", ".json5", ".js", ".ets", ".map")):
                    hits.extend({"file": name, **hit} for hit in findings(package.read(name).decode(errors="replace")))
    if not checked:
        raise RuntimeError("HAP contains no audited ABC modules")
    return {"sha256": hashlib.sha256(hap.read_bytes()).hexdigest(),
            "abc_modules_checked": checked, "findings": hits, "passed": not hits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--hap", type=Path)
    parser.add_argument("--disassembler", type=Path)
    args = parser.parse_args()
    if args.hap and not args.disassembler:
        parser.error("--hap requires --disassembler")
    if not args.repo and not args.hap:
        parser.error("provide --repo and/or --hap")
    results = {}
    if args.repo:
        results["source"] = audit_source(args.repo, args.ref)
    if args.hap:
        results["hap"] = audit_hap(args.hap, args.disassembler)
    print(json.dumps(results, indent=2))
    return 0 if all(r["passed"] for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
