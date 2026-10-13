# Business-only case structure

Each `cases/<id>/` contains `case.json`, `fix.patch` and `testcase/`, whose files
are the HapRay Python testcase and descriptor, its `.workload.json` UI plan and
`workload_driver.py`. Copy **all** testcase files to the declared `install_dir`.

## Source and build contract

`hosts_patches/host-reconstruction.json` records every original business tree.
`clean/<id>/<variant>` identifies that state; `clean-app/<id>/<variant>` adds only
explicitly recorded production adaptations. The browser clear-history button,
for example, calls the existing database deletion operation in **both** variants.
No test branch, measurement counter, custom trace or app-side gate is allowed.

Use `python3 tools/reconstruct_clean_hosts.py`; `--seed-root` can reuse local
clones. Supplemental historical business states are recovered from the repair
diffs and exact tree hashes must match. Trees, not regenerated commit IDs, are
stable reconstruction identities.

`tools/build_clean_cases.py` uses isolated worktrees, locked dependencies, release
builds and disassembly of every ABC module. Formatting-only ohpm metadata is
restored; dependency/business-source modifications fail the build. Identical
source trees may reuse only a hash-checked, audited compiled artifact.

## External workload contract

UI plans declare `setup`, `measured` and `verify` actions driven through `uitest`.
Their existence or syntax validity does not prove successful reproduction. The
plans must reach the actual business path in both variants on the real device.

Prepare data outside profiling, using normal operations, external services or
offline database/preference fixtures. `tools/seed_browser.py` creates ordinary
SQLite history; `tools/install_sqlite_fixture.py` stops the app, backs up existing
data, then installs the fixture. Direct database preparation requires a root test
device. Keep fixture metadata and expected results outside the agent sandbox.

CloudMusic local-song preparation uses actual MP3 files and the app's ordinary
SQLite schema. `songFile` is relative to `filesDir`, as in the normal import path;
local tracks use `songId=0`. No player callbacks are synthesized.

```bash
python3 tools/seed_local_songs.py artifacts/fixtures/cloudmusic-relative-mp3 --count 10000
python3 tools/validate_external_workloads.py cloudmusic_local_song_memory_filter \
  --local-song-fixture artifacts/fixtures/cloudmusic-relative-mp3
python3 tools/capture_external_cpu.py cloudmusic_local_song_memory_filter \
  --variant unfixed --round 1 --local-song-fixture artifacts/fixtures/cloudmusic-relative-mp3
```

Generation requires `ffmpeg`; device preparation backs up the existing database
and verifies the deployed audio. Fixture identity includes database, filename
manifest and audio content. These commands prepare/capture evidence only; they do
not themselves establish that a case passes its performance oracle.

```bash
python3 tools/ui_driver.py cases/<id>/testcase/<name>.workload.json --remote cityuPC --phase setup
python3 tools/ui_driver.py cases/<id>/testcase/<name>.workload.json --remote cityuPC --phase measured
python3 tools/ui_driver.py cases/<id>/testcase/<name>.workload.json --remote cityuPC --phase verify
```

## Independent acceptance gates

1. Exact clean source trees and business-only repair diff.
2. Both release builds and compiled-bytecode audits pass.
3. Signed variants install, stay running and display foreground app UI.
4. External fixtures and actions reach the faulty business path in both variants.
5. Measure the declared system CPU/memory metric over >= 3 rounds per variant;
   demonstrate `unfixed >= 1.2 * fixed`, using identical data/actions and preserving
   functional correctness. The capture window must cover the entire action sequence.

`case.json#clean_validation` records the stages separately. Workload/performance
statuses remain pending until actual evidence exists. Legacy instrumented results
are archived under `test_oracle.legacy_instrumented_evidence`; the old measurement
contract is in `validation/legacy-measurement-contract.json`. Neither is clean
validation evidence. Install/build success is not a performance verdict.
