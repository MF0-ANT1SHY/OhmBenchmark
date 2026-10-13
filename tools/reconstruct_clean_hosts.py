#!/usr/bin/env python3
"""Reconstruct business-only case trees, never applying measurement patches."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args, **kwargs):
    return subprocess.check_output(["git", "-C", str(repo), *args], **kwargs).decode().strip()


def reconstruct(host, info, seed_root=None):
    repo = ROOT / "hosts" / host
    repo.parent.mkdir(exist_ok=True)
    if not repo.exists():
        seed = seed_root / host if seed_root else None
        source = str(seed) if seed and seed.is_dir() else info["upstream_repository"]
        subprocess.run(["git", "clone", "--no-hardlinks", source, str(repo)], check=True)
    if git(repo, "status", "--porcelain"):
        raise RuntimeError(f"refusing to modify dirty host: {repo}")
    reachable = {}
    for line in git(repo, "log", "--all", "--format=%T %H").splitlines():
        tree, commit = line.split()
        reachable[tree] = commit
    base = git(repo, "rev-parse", info["upstream_base_commit"])
    if any(entry["tree"] not in reachable for entry in info["case_tags"].values()):
        git(repo, "checkout", "--detach", base)
        # A seed may already contain the patch series. Apply only if the series' trees
        # are missing; recovered variant-specific states are handled below.
        series = sorted((ROOT / "hosts_patches" / host).glob("[0-9]*.patch"))
        first_patch = series[0]
        subject = first_patch.read_text().split("Subject: ", 1)[1].split("\n\n", 1)[0]
        subject = " ".join(subject.split()).split("] ", 1)[-1]
        subjects = git(repo, "log", "--all", "--format=%s").splitlines()
        if subject not in subjects:
            git(repo, "-c", "user.name=OhmBenchmark", "-c", "user.email=benchmark@localhost",
                "am", *map(str, series))
        reachable = dict(line.split() for line in
                         git(repo, "log", "--all", "--format=%T %H").splitlines())
    for tag, entry in info["case_tags"].items():
        clean_tag = tag.replace("case/", "clean/", 1)
        tree = entry["tree"]
        if tree not in reachable:
            _, cid, variant = tag.split("/")
            other = "fixed" if variant == "unfixed" else "unfixed"
            other_tree = info["case_tags"][f"case/{cid}/{other}"]["tree"]
            if other_tree not in reachable:
                raise RuntimeError(f"cannot recover {tag}: opposite tree is missing")
            git(repo, "checkout", "--detach", reachable[other_tree])
            args = ["apply", "--index"]
            if variant == "unfixed":
                args.append("--reverse")
            git(repo, *args, str(ROOT / "cases" / cid / "fix.patch"))
            actual = git(repo, "write-tree")
            if actual != tree:
                raise RuntimeError(f"{tag}: recovered tree {actual} != expected {tree}")
            git(repo, "-c", "user.name=OhmBenchmark", "-c", "user.email=benchmark@localhost",
                "commit", "-m", entry["state"])
            reachable[tree] = git(repo, "rev-parse", "HEAD")
        existing = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", clean_tag],
                                  capture_output=True, text=True)
        if existing.returncode == 0:
            if git(repo, "rev-parse", f"{clean_tag}^{{tree}}") != tree:
                raise RuntimeError(f"existing tag has wrong tree: {host}/{tag}")
        else:
            git(repo, "tag", clean_tag, reachable[tree])
        app_tag = entry.get('app_ref', tag.replace("case/", "clean-app/", 1))
        app_tree = entry.get("app_tree", tree)
        app_existing = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", app_tag],
                                      capture_output=True, text=True)
        if app_existing.returncode == 0:
            if git(repo, "rev-parse", f"{app_tag}^{{tree}}") != app_tree:
                raise RuntimeError(f"existing app tag has wrong tree: {host}/{app_tag}")
        else:
            git(repo, "checkout", "--detach", reachable[tree])
            for patch in entry.get("production_patches", []):
                git(repo, "apply", "--index", str(ROOT / patch))
            if git(repo, "write-tree") != app_tree:
                raise RuntimeError(f"production patches do not reproduce {app_tag}")
            if entry.get("production_patches"):
                git(repo, "-c", "user.name=OhmBenchmark", "-c", "user.email=benchmark@localhost",
                    "commit", "-m", "build: apply recorded production adaptation")
            git(repo, "tag", app_tag, "HEAD")
        print(f"{host} {tag} {tree}", flush=True)
    return repo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hosts", nargs="*")
    parser.add_argument("--seed-root", type=Path, help="optional local clone cache")
    args = parser.parse_args()
    metadata = json.loads((ROOT / "hosts_patches/host-reconstruction.json").read_text())
    for host in args.hosts or metadata["hosts"]:
        reconstruct(host, metadata["hosts"][host], args.seed_root)


if __name__ == "__main__":
    main()
