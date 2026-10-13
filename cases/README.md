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

Jingmo random-poem preparation also uses ordinary database rows:

```bash
python3 tools/seed_classic_poems.py artifacts/fixtures/jingmo/jingmo.db --count 100000
python3 tools/validate_external_workloads.py jingmo_random_poem_orderby_random \
  --poem-fixture artifacts/fixtures/jingmo/jingmo.db
```

The evaluator checks displayed title/content against the database and observes
different poems across repeated UI refreshes. No simulated scans, app counters
or in-app completion flags are used. Run this only when the device is not already
collecting another case's profile.

YTMusic playback can use its original packaged MP3 files with `--bundled-audio`.
The evaluator hashes the actual audited HAP's audio entries and verifies they are
identical across the pair; no audio events or player callbacks are synthesized.
The current-playing workload observes 60 seconds of normal playback. External
accessibility snapshots must show the app's slider advancing with elapsed time;
the validator and each CPU capture check this, and acceptance recomputes the
progress proof from raw snapshots. A visible song title alone is not sufficient.

SepWeather font preparation uses `--bundled-fonts`, which hashes the real TTF/OTF
assets from the audited HAP and requires the two fonts registered by MainPage.
`validation/sepweather-bundled-fonts.json` proves identical packaged fonts across
the pair, not repeated page creation or a CPU improvement. The current launch
flags still need device lifecycle verification; a visible AddAddress button alone
cannot prove MainPage was reconstructed in the same process. The validator and
each capture archive native window identities plus raw process stat/cmdline;
acceptance requires ten new ability windows in one unchanged process. Reused
windows, process restarts or a summary differing from those observations fail.

CloudMusic online-list preparation uses the existing server configuration UI and
ordinary music API responses from `tools/cloudmusic_data_service.py`. The
settings plan is `tools/fixtures/cloudmusic-api-setup.workload.json`, using the
normal My/Settings/Cloud Service pages. Its real-device configuration proof is
`validation/cloudmusic-online-setup.json`; this is not a list/performance verdict.
Run the service on the device workstation,
then, when the device is idle, use `hdc rport tcp:18490 tcp:18490` and the normal
settings plan to configure `http://127.0.0.1:18490`. This does not add app endpoints
or change application code. Use `--music-service` with the workload validator and
CPU collector for the three online-list cases. Each trial hashes the complete
ordinary catalogue before/after the workload and checks service continuity;
workload validation also checks song titles and artist text against that data.
Each pair still needs its own actual workload and performance acceptance.

SheafReader data preparation uses `tools/rss_data_service.py`: ten ordinary RSS
subscriptions, each with one hundred stable articles and long HTML descriptions,
plus an OPML subscription document. `/feeds/1.xml` through `/feeds/10.xml`,
`/subscriptions.opml` and the linked article pages are normal content routes;
there are no benchmark status/oracle endpoints. Default payloads stay below the SDK's
default 5 MiB HTTP response limit. Local XML and workstation HTTP checks are in
`validation/rss-data-fixture.json` and `validation/rss-data-service.json`.
Device forwarding, subscription/import UI, actual refreshes and performance
acceptance remain pending. When the device is idle, forward port 18491 and use
the app's normal feed URL/import controls; do not replace them with an app hook.
The source-grounded phone subscription candidate is
`tools/fixtures/sheafreader-add-feed.workload.json`. Its drawer-button and fresh
URL assumptions are recorded in `validation/rss-subscription-plan.json`; neither
file proves successful device subscription or article ingestion.

```bash
python3 tools/ui_driver.py cases/<id>/testcase/<name>.workload.json --remote cityuPC --phase setup
python3 tools/ui_driver.py cases/<id>/testcase/<name>.workload.json --remote cityuPC --phase measured
python3 tools/ui_driver.py cases/<id>/testcase/<name>.workload.json --remote cityuPC --phase verify
```

## Independent acceptance gates

For `app_pss_bytes` cases, `tools/capture_external_pss.py` records the kernel's
`/proc/PID/smaps_rollup` total `Pss` before, during and after normal UI actions.
The value is the final absolute app PSS, not RSS, growth, system memory or a
selected minimum. Process name and start time must remain consistent throughout
the trial; UI/observer failures and restarts invalidate collection. The reader
has a real-device check in `validation/system-pss-device-check.json`, but that
does **not** validate a memory case. `tools/accept_pss_evidence.py` recomputes all
six windows and the unchanged 1.2x paired criterion. For the search-history case,
it also verifies fresh per-trial ordinary preference preparation and UI reading;
actual case acceptance remains pending. WanHarmony input preparation is not yet
implemented, so its memory gate stays closed. The collector never inherits a
previous validation run's fixture hash as fresh preparation evidence.

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
