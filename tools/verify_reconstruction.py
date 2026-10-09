#!/usr/bin/env python3
"""Verify a reconstructed host repository against hosts_patches/host-reconstruction.json.

Every case tag in the dataset resolves to an exact source tree. Because `git am` stamps
fresh committer dates, reconstructed commit SHAs differ from the originals, so this
compares TREES, which are stable and are what the measured HAPs were actually built from.

Usage:
    python3 tools/verify_reconstruction.py <host> [repo-path]

    python3 tools/verify_reconstruction.py browser hosts/browser
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METADATA = ROOT / "hosts_patches" / "host-reconstruction.json"


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL
    ).decode().strip()


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2

    host = sys.argv[1]
    repo = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "hosts" / host

    doc = json.loads(METADATA.read_text(encoding="utf-8"))
    if host not in doc["hosts"]:
        print(f"unknown host {host!r}; known: {', '.join(doc['hosts'])}")
        return 2
    if not (repo / ".git").exists():
        print(f"not a git repository: {repo}")
        return 2

    info = doc["hosts"][host]
    print(f"host         : {host}")
    print(f"repository   : {repo}")
    print(f"upstream     : {info['upstream_repository']} @ {info['upstream_base_commit']}")
    print()

    # Every tree reachable in the reconstruction, so we can tell "absent" from "wrong".
    reachable = {}
    for line in git(repo, "log", "--all", "--format=%T %H %s").splitlines():
        tree, sha, subject = line.split(" ", 2)
        reachable.setdefault(tree, (sha, subject))

    ok = missing = 0
    for tag in sorted(info["case_tags"]):
        want = info["case_tags"][tag]["tree"]
        state = info["case_tags"][tag]["state"]
        if want in reachable:
            sha, subject = reachable[want]
            print(f"  OK    {tag}")
            print(f"        tree={want[:12]} commit={sha[:12]}")
            print(f"        {subject}")
            ok += 1
        else:
            print(f"  MISS  {tag}  expected tree={want[:12]}  ({state})")
            missing += 1

    print()
    print(f"{ok} verified, {missing} missing")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
