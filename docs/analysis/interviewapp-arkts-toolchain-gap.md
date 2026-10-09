# interviewapp: solved by installing the 5.0.5 toolchain

## The gap, and the fix

Building `interviewapp` with the 5.1.0 command-line tools produced **38 ArkTS strict-rule errors
across 15 application files** (`arkts-no-any-unknown`, `arkts-no-implicit-return-types`,
`arkts-no-spread`). The host declares `compatibleSdkVersion: 5.0.0(12)`, so the 5.1 compiler was
applying rules the source predates.

**Fixed by installing the matching toolchain**, not by editing the app:

```
commandline-tools-linux-x64-5.0.5.310.zip   3,240,302,021 bytes
sha256  f5b4240807c24457294b6469c6d39c1c00b5d9e06c391852d633a5da7ff28c6d
        (verified against the published .sha256)
from    https://repo.huaweicloud.com/harmonyos/ohpm/5.0.5/
```

Installed at `/home/research/OhmBenchmark-toolchain-5.0.5`, beside the 5.1.0 tools.

**Verified**: a clean checkout of the unfixed commit, with no source changes, builds with
`BUILD SUCCESSFUL` under 5.0.5. The same tree yields 38 errors under 5.1.0. The app was never
broken.

## Wiring

| file | role |
| --- | --- |
| `device-tests/toolchain.sh` | selects a toolchain version and exports `PATH` + `DEVECO_SDK_HOME` |
| `device-tests/host_toolchain.txt` | which hosts need which version; 5.1.0 remains the default |

The driver derives the host from the case spec, looks the version up, and sources it before
`ohpm` and `hvigor` run. Hosts not listed keep using 5.1.0.

## Why not patch the 38 errors

The unfixed and fixed commits do not contain identical code, so every edit would need making
twice and keeping consistent. Editing 15 application files to satisfy a compiler the case was
never written for changes the artifact being measured. Installing the right compiler is both
smaller and more faithful.

**This likely helps other hosts too.** Any host declaring a pre-5.1 `compatibleSdkVersion` will
hit the same wall, and should be added to `host_toolchain.txt` rather than patched.

## What now works for interviewapp_response_log_full_stringify

- builds under 5.0.5, signs, installs, and reaches `state=ready` on the device;
- the instrumenter finds the one full-body serialization on the unfixed shape and correctly
  reports none on the fixed shape;
- the counter is published through `commons/basic/Index.ets`, the package's public surface -
  not by re-exporting from `request.ets`, which perturbed module initialisation and made the app
  fail before the bench logged anything;
- the fixture serves a **345,818-byte** body with 1000 rows on `127.0.0.1:18766`, reachable over
  `hdc rport`.

## The remaining problem

The bench reaches `ready`, is released, then reports `{"state":"error","message":"[object
Object]"}` with an **empty diag log** - so the failure is in the measured action, before its
first checkpoint. The action performs five HTTP GETs against the fixture.

Most likely causes:

1. **The device cannot reach the fixture.** `hdc fport ls` shows the reverse forward registered
   (`tcp:18766 tcp:18766 [Reverse]`), but a second `hdc rport` for the same port is rejected
   with "TCP Port listen failed", so the forward may be stale from an earlier session. Removing
   it (`hdc fport rm`) and re-adding it, then confirming the device can fetch the URL, is the
   first check.
2. **The response shape does not satisfy the handler.** It requires `code === 10000`; the
   fixture returns exactly that, so this is less likely but cheap to rule out.
3. **`ohmHttp.baseURL` set in `prepare()` is not the instance the call uses.** The harness sets
   it on the imported singleton; worth confirming the request actually goes to 127.0.0.1.

The error message is `[object Object]` because the probe stringifies the exception with
`String(e)`; capturing `e.message` as well would make the next failure self-describing, which is
the same lesson as the ytmusic diagnostic.
