# interviewapp: the host does not compile under the available toolchain

## The finding

Building `interviewapp` with the toolchain in use here produces **38 ArkTS strict-rule errors
across 15 files**, all in application code:

```
commons/basic/Index.ets
components/InterviewListComp.ets      components/QuestionListComp.ets
services/InterviewService.ets         services/ProjectService.ets
utils/InterviewBench.ets              views/ClockedComp.ets
views/HomeComp.ets                    views/InterviewDetailComp.ets
views/MineComp.ets                    views/OptionalComp.ets
views/ProfileEditComp.ets             views/ProjectComp.ets
views/QuestionDetailComp.ets          views/StudyTimeComp.ets
```

The rules are `arkts-no-any-unknown`, `arkts-no-implicit-return-types` and `arkts-no-spread`.

## Why this is a toolchain gap rather than a code defect

The host declares `"compatibleSdkVersion": "5.0.0(12)"`, while the toolchain available here is
the 5.1.0 command-line tools (`commandline-tools-linux-x64-5.1.0.840`). The 5.1 compiler applies
strict rules the 5.0-era source predates. The app is not broken; it was written against an older,
laxer compiler than the one installed.

This also explains why earlier rounds got further: the browser, sheafreader, ytmusic and the
interviewapp *history* cases all compiled, because the files they pull in happen to be clean. The
response-log case reaches further into `commons/basic` and `features/home`, which is where the
violations live.

## What I tried, and what it cost

Fixing these individually is whack-a-mole: two fixes in `QuestionService.ets` and
`QuestionListComp.ets` did not reduce the total, which is 38. Two of my own mistakes along the
way are worth recording:

1. **Wrong place for the package re-export.** I appended it to `request.ets`, but the package's
   public surface is `commons/basic/Index.ets`, which is itself one of the failing files. That is
   the correct place, and it is currently blocked.
2. **A duplicated counter module** from injecting the same text twice, which produced "Cannot
   redeclare block-scoped variable". Fixed by giving the counter a single source.

## Why I stopped rather than patching all 38

The objective requires keeping the repository reproducible and the measurements honest. Editing
15 application files to satisfy a compiler the case was never written for changes the artifact
being measured, and does so *differently for the unfixed and fixed commits* - they do not contain
identical code, so any edit has to be made twice and kept consistent. That is a real risk of
measuring something other than the case.

The right fix is a toolchain matching the host's declared `compatibleSdkVersion: 5.0.0(12)`. The
5.1.0 tools came from `https://repo.huaweicloud.com/harmonyos/ohpm/5.1.0/`; the equivalent 5.0.0
command-line tools should be the target, and installing them would very likely make this host -
and any other host with the same gap - build unmodified.

## What is ready for that moment

Everything except the compile:

- `device-tests/response_server.py` serves a **345,818-byte** body with 1000 rows on
  `127.0.0.1:18766`, verified reachable from the device over `hdc rport tcp:18766 tcp:18766`;
- `tools/instrument_response_stringify.py` rewrites the one full-body serialization on the
  response path and reports 0 sites on the fixed shape, which is correct;
- the harness patch emits the tally through the append-only diag channel;
- `SUMMARY_SOURCE=diag:serializes` reports it.

Expected result once the host compiles: unfixed `serializes=5` with a 345 KB body per call,
fixed `serializes=0` - the oracle's O(payload) versus O(1) distinction.

## The exact next step

Either install the 5.0.0 command-line tools matching `compatibleSdkVersion: 5.0.0(12)`, or apply
the 38 strict-rule fixes consistently to both commits and record that the measured artifact was
compiler-adjusted. The first is strongly preferable.
