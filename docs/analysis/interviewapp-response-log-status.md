# interviewapp_response_log_full_stringify: instrumentation done, build blocked elsewhere

## The case

Declared metric `response_handler_cpu_ms` - "CPU time spent in the HTTP response handling path
per API call". The unfixed handler logs
`JSON.stringify(res.result).substring(0, 200)`, serializing the entire response body to keep 200
characters; the fixed handler logs two fields. The oracle states the cost driver itself:
"unfixed serializes each full response body (O(payload)); fixed logs O(1) fields".

## Fixture prepared and verified

- `device-tests/response_server.py` serves a **345,818-byte** body with **1000 rows** on
  `127.0.0.1:18766`, which the bench points `ohmHttp.baseURL` at;
- the device reaches it through a reverse forward:
  `hdc rport tcp:18766 tcp:18766` (confirmed: `Forwardport result:OK`, `[Reverse]`);
- a WSL-side fetch of `/response` returns the payload, so the fixture itself is sound.

This is the first time this case's fixture has been stood up, and it is reusable for any other
interviewapp HTTP case.

## Instrumentation done

`tools/instrument_response_stringify.py`:

- rewrites the one full-body serialization on the response path,
  `JSON.stringify(res.result)` -> `ohmResponseStringify(res.result)`;
- writes the counter module to `commons/basic/src/main/ets/utils/OhmResponseCount.ets`;
- re-exports the counter from `request.ets`, because a new file under that package is **not**
  automatically part of `@itcast/basic`;
- on the fixed commit it finds no serialization to rewrite and says so, which is correct - the
  fixed shape has nothing to count, so the metric legitimately reads 0.

The bench writes its tally through the append-only diag helper, the channel proven to survive
where the status file overwrote diagnostics.

## Where the build stops, and why it is not this case

The instrumentation itself compiles; the import chain resolves. The build then fails on files
that belong to the application and have nothing to do with this case:

```
arkts-no-implicit-return-types   features/home/.../services/QuestionService.ets:12:10
arkts-no-implicit-return-types   features/home/.../services/QuestionService.ets:16:10
arkts-no-any-unknown             features/home/.../components/QuestionListComp.ets:42:13
arkts-no-spread                  features/home/.../components/QuestionListComp.ets:43:22
```

Three earlier build failures in this round *were* mine and are fixed: a circular import
(`commons/basic` cannot import from `features/home`), a duplicated counter file from a bad
string injection ("Cannot redeclare block-scoped variable"), and the missing package re-export.

The remaining errors are strict ArkTS rules in application code, reached because the module
graph now pulls those files in. They need either small explicit-type fixes in the host or a
build-mode adjustment; either way it is a host-compatibility problem rather than a measurement
problem, and it is the last thing between this case and a run.

## Exact next command

```bash
cd /home/research/OhmBenchmark-main
python3 device-tests/response_server.py &          # fixture on 18766
hdc rport tcp:18766 tcp:18766                      # device reaches it
SUMMARY_SOURCE=diag:serializes bash device-tests/run_declared_metric.sh \
  interviewapp_response_log_full_stringify interviewapp 6f1c96f 4fd3756 \
  tools/instrument_response_stringify.py 3
```

Expected once the host compiles: unfixed `serializes=5` (one full-body serialization per call,
with a 345 KB body each), fixed `serializes=0`, which is the oracle's O(payload) versus O(1)
distinction.
