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

`ytmusic` was the one host with no git bundle, because its upstream repository carries
~350 MB of rawfile audio at tip. It has since been reconstructed with the same procedure,
fetching only the base commit:

```bash
NAME=ytmusic
URL=https://github.com/Charles-Stark/Youtube-Music-ArkTS-Clone
BASE=f925981            # this is the tip of upstream `main`
git init hosts/$NAME && cd hosts/$NAME
git remote add origin "$URL"
git fetch --depth 1 origin main      # sidesteps the 350 MB audio history
git checkout FETCH_HEAD
git checkout -b ohmbase
git am ../../hosts_patches/ytmusic/*.patch
```

All four patches apply cleanly. The resulting dataset states are:

| reconstructed commit | subject | role |
| --- | --- | --- |
| `b708e3855768` | build: strip signing, move screenshots | unfixed for `history_json_parse_per_row` |
| `6e5d4f8c79e7` | parse each history entry's JSON once | fixed for `json_parse`, unfixed for `search_no_debounce` |
| `73d702e49b2e` | debounce search by 300ms | fixed for `search_no_debounce`, unfixed for `current_playing_timeupdate` |
| `f80bfeac1b99` | update progress only on second change | fixed for `current_playing_timeupdate` |

(The values above are tree hashes, which is what `host-reconstruction.json` records and what
`tools/verify_reconstruction.py` checks; `git am` rewrites commit SHAs.)

## Verifying a reconstruction

`host-reconstruction.json` gives, for every case tag, the exact tree hash of the code state
that was built and measured. Check your rebuild with the bundled tool:

```bash
python3 tools/verify_reconstruction.py browser hosts/browser   # or ./tools/verify_reconstruction.py
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
