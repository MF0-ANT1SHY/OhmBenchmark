# Reconstructing the host repositories

The dataset's exact unfixed/fixed code states are reconstructed from **public upstream
repositories plus the patch series in this directory**. No git bundles are stored in this
repository; `host-reconstruction.json` records everything needed to verify a rebuild.

## Procedure

For each row of the table in `README.md`:

```bash
NAME=browser
URL=https://github.com/langwudong/browser     # upstream_repository
BASE=f44fff7                                   # upstream_base_commit
PATCHES=hosts_patches/$NAME                    # ordered *.patch series

git clone "$URL" hosts/$NAME
git -C hosts/$NAME checkout "$BASE"
git -C hosts/$NAME checkout -b ohmbase
git -C hosts/$NAME am "$PWD"/$PATCHES/*.patch
```

`git am` applies the series in filename order. Every series applies cleanly onto its
recorded base commit; this has been verified for all 8 hosts.

### ytmusic

`ytmusic` has no upstream-base row in the bundle metadata because its upstream repository
carries ~350 MB of rawfile audio at tip. Use the same procedure with
`URL=https://github.com/Charles-Stark/Youtube-Music-ArkTS-Clone` and `BASE=f925981`; the
patch series reconstructs the code without duplicating that history.

## Verifying a reconstruction

`host-reconstruction.json` gives, for every case tag, the exact tree hash of the code state
that was built and measured. Check your rebuild with the bundled tool:

```bash
python3 tools/verify_reconstruction.py browser hosts/browser
```

It walks every case tag for that host and reports whether the expected tree is present,
naming the reconstructed commit and subject for each match. Exit code 0 means all tags
verified.

Because `git am` stamps new committer dates, the **commit SHAs differ** from the ones
`cases/<id>/case.json` records, but the **trees are identical** — the same source that was
built into the measured HAPs. Compare trees, not commit hashes.

Two tags map to the upstream base itself (`upstream-base:<sha>` in the JSON): those cases
use the unmodified upstream code as the unfixed state.

## Tagging after reconstruction

`cases/<id>/case.json` records the original `unfixed_commit` / `fixed_commit`. Once you have
reconstructed and verified the trees, tag your own commits as
`case/<id>/{unfixed,fixed}` to reproduce the original workflow ergonomics.
