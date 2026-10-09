# cloudmusic cannot be installed from a self-signed build

## The blocker, confirmed twice

```
error: failed to install bundle. code:9568289
error: install failed due to grant request permissions failed.
PermissionName: ohos.permission.SYSTEM_FLOAT_WINDOW
```

`ohos.permission.SYSTEM_FLOAT_WINDOW` is a **system-grant** permission: only applications signed
with a system-level profile can be granted it, so a locally signed debug build is rejected at
install. Every run then times out for want of an app to drive.

This blocks **all the cloudmusic cases**, which share one bundle and permission set. It is the same
class of environment constraint as the fixture-reachability limit, and is recorded once rather than
rediscovered per case.

## Attempted mitigation, and why it did not land

`SYSTEM_FLOAT_WINDOW` gates `WindowUtils.ets`' float-window creation, which is unrelated to the
`PLAY_TIME` writes this case declares, so removing the request is a defensible minimal deviation -
applied identically to both variants, so the comparison stays fair.

`tools/instrument_play_time.py` therefore removes the entry from `entry/src/main/module.json5` by
matching braces (a rigid regex did not match and silently left it in place, which is why the first
attempt produced the identical install error). The removal itself is verified:

- `module.json5` no longer mentions `SYSTEM_FLOAT_WINDOW`;
- the file still parses and its braces balance.

It did **not** reach the installed artifact, because the build failed before packaging, and
`hdc install` then installed the **stale HAP from the previous build** - which still carried the
permission. That is worth stating plainly: the install error in that run says nothing about whether
the removal works.

## The build failure that masked it

```
Error Message: Cannot find module '../../OhmPlayTimeCount' or its corresponding type declarations.
  At File: .../common/utils/play/AVPlayerUtils.ets:11:29
```

The counter module is not present at build time. Two candidate causes, not yet distinguished:

1. **Clean-after-instrument ordering.** The driver checks out, cleans, applies the harness patch,
   then runs the instrumenter - correct. But the instrumenter's own untracked additions are made
   after that clean, and any later `git clean` in the same variant would remove them. Worth
   confirming the driver never cleans again before building.
2. **The module is written outside the build's source root.** It is written to
   `entry/src/main/ets/common/utils/`, which is inside the module, so this is less likely - but the
   resolve failure names the importing file and the path it tried, and the file's presence at that
   moment has not been verified in the same shell invocation as the build.

The next diagnostic is small: after the instrumenter runs and immediately before the build, list
the counter file and print `git status --porcelain` for the host. If the file is present and the
build still fails, the resolution is the problem; if absent, the ordering is.

## What is built and correct regardless

`tools/instrument_play_time.py` prepares `cloudmusic_play_time_high_frequency_update`
(`player_page_rerenders_per_minute`) following the pattern proven on ytmusic and wanharmony:

- counts the actual `AppStorage.setOrCreate(StorageConstants.PLAY_TIME, time)` write site, so real
  playback would also be measured;
- writes `OhmPlayTimeCount.ets` under `common/utils/` - there is no `entry/.../ets/utils/` in this
  host - carrying the variant's guard as a callable, the guard's state commit (without which the
  fixed variant would admit every tick and the two would be indistinguishable), and the
  `ready`/`ohm-go` handshake;
- installs a bench on `EntryAbility.onNewWant` that drives the guard over the 600 ticks one minute
  of playback produces and writes the terminal status.

Expected once installable: unfixed **600** writes, fixed **60** - the oracle's 10/s versus 1/s.

Three build errors were fixed on the way: the counter's location (no `ets/utils/` in this host);
imports inserted after code, because `EntryAbility.ets` has a statement before its imports, so both
edit sites now anchor on the last import line; and the relative depth, which the host's own
`'../../constants/...'` imports settle at two levels.

## What would unblock it

A signing profile entitled to `SYSTEM_FLOAT_WINDOW`, or the permission removed and the build made
to succeed - which is what the code above attempts and what the build failure currently prevents.

## Re-run command

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:writes bash device-tests/run_declared_metric.sh \
  cloudmusic_play_time_high_frequency_update cloudmusic 2aa4715 d755085 \
  self-installing:tools/instrument_play_time.py 3
```
