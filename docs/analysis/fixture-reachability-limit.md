# Fixture-dependent cases cannot be measured in this environment

## The finding

Several cases drive the app against a **local HTTP fixture**. In this environment that fixture
cannot be reached from the device, and the reason is environmental rather than a defect in the
repository.

Established by measurement, not assumption:

| arrangement | result |
| --- | --- |
| fixture in WSL, `hdc rport tcp:18766 tcp:18766` | registers `[Reverse]`; app reports `code=2300056 Failure when receiving data from the peer`; fixture access log stays empty |
| fixture in WSL, `hdc fport tcp:18766 tcp:18766` | registers `[Forward]`; app reports `code=2300007 Couldn't connect to server`; fixture access log stays empty |
| fixture in WSL, app pointed at the WSL address `172.25.36.54` | WSL itself fetches it fine (HTTP 200, 345,818 bytes), but that address is NAT-internal and not routable from a physical phone on USB |
| fixture on the **Windows** host at `10.10.48.229` | `HttpListener` refuses to bind: `Access is denied` - binding a non-loopback address requires elevation, which this session does not have |

The device carries neither `curl` nor `wget`, so it cannot probe the path itself; the app's own
error codes are the only reachability signal available.

## Why the error reporting was the enabling step

Earlier rounds saw only `{"state":"error","message":"[object Object]"}`, which is what
`String(BusinessError)` produces. Reporting `name`/`code`/`message` turned that into a specific,
actionable code and made this whole table possible. It is the single most valuable change of the
last four rounds and applies to every future HTTP case.

## What this means for the objective

The following cases depend on a fixture the device must reach, and **cannot be measured here**
without one of: an elevated Windows listener, a fixture reachable over the phone's own network,
or a routing change on the Windows host:

- `interviewapp_response_log_full_stringify` (fixture: `response_server.py`, 345 KB body)
- the browser cases, which point `baseURL` at `127.0.0.1:18766`
- `weatherassistant_remote_weather_icons` and the weather assistant cases (`weather_server.py`,
  port 18767)
- the sheafreader cases (`rss_server.py`, port 18765)

This is a **systemic constraint**, not a per-case one, and it is worth stating plainly rather
than rediscovering it case by case. Cases that measure purely on-device - counts of statements,
queries, flushes, entries, parses, state updates - are unaffected and are the ones that have been
measured successfully.

## What is nonetheless done for this case

Everything except the network path:

- builds under the 5.0.5 toolchain (`device-tests/toolchain.sh`, `host_toolchain.txt`);
- the harness patch is now **generated** by `tools/build_harness_patch.py`, so its hunk counts
  cannot drift - hand-editing a section and forgetting to update `@@ -0,0 +1,N @@` makes
  `git apply` silently truncate the file, which cost two rounds here;
- `tools/instrument_response_stringify.py` instruments the one serialization site, preserves the
  instrumented file's length, exports the counter through `commons/basic/Index.ets`, and takes
  `--fixture-host` so the bench can be pointed at any reachable address;
- the bench reaches `state=ready`, is released, and runs its measured action;
- expected result once reachable: unfixed `serializes=5`, fixed `serializes=0`.

## The one-command re-run, should a fixture become reachable

```bash
cd /home/research/OhmBenchmark-main
python3 device-tests/response_server.py &        # or a Windows-side equivalent
hdc rport tcp:18766 tcp:18766                    # or whichever direction works
SUMMARY_SOURCE=diag:serializes bash device-tests/run_declared_metric.sh \
  interviewapp_response_log_full_stringify interviewapp 6f1c96f 4fd3756 \
  tools/instrument_response_stringify.py 3
```
