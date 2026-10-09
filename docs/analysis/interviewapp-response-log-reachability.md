# interviewapp_response_log_full_stringify: the build is fixed; the fixture is unreachable

## Where the case stands

The case now builds, signs, installs, reaches `state=ready`, is released, and runs its measured
action. The declared-metric instrumentation works: on the unfixed shape it routes the one
full-body serialization through the counter, and on the fixed shape it correctly finds nothing to
count.

What it cannot do yet is **reach its fixture**, and the newly descriptive error reporting is what
established that:

```
code=2300056  Failure when receiving data from the peer     (rport forwarding in place)
code=2300007  Couldn't connect to server                    (fport forwarding in place)
```

The fixture's own access log shows **no request ever arrives**, which confirms these are
connection failures rather than response-shape problems.

## Why the error reporting mattered

Before this round the same failure read `{"state":"error","message":"[object Object]"}` - three
device cycles produced no usable information, because `String(BusinessError)` yields exactly
that string. Reporting `name`/`code`/`message` turned an opaque failure into a specific one in a
single run. That change is worth more than the case itself for every future HTTP case.

## The environment constraint

The fixture runs inside WSL, whose address here is `172.25.36.54` - a NAT-internal address. The
attached device is a physical phone over USB, so that address is not routable to it, and the
`hdc` port-forward directions do not bridge the gap:

| rule | meaning | observed |
| --- | --- | --- |
| `hdc rport tcp:18766 tcp:18766` | device port -> local host | registers `[Reverse]`, traffic does not arrive |
| `hdc fport tcp:18766 tcp:18766` | local traffic -> remote device | registers `[Forward]`, app reports "Couldn't connect to server" |

A check of whether the device can open a socket to the WSL address was **inconclusive and
should not be trusted**: `cat < /dev/null > /dev/tcp/...` was used, but `/dev/tcp` is a bash
feature and the device shell is `sh`, so both the test and its control failed identically. A
device-side reachability probe needs a tool the phone actually has.

## The likely fix

Run the fixture on the **Windows** side rather than inside WSL. The device is attached to
Windows, so a listener there is reachable through the USB/RNDIS network, and `hdc fport` can
bind it to the device's loopback. `device-tests/response_server.py` is a handful of lines of
`http.server` and binds to a configurable host, so it can run under Windows Python unchanged;
only the bind address needs to change from `127.0.0.1` to the Windows interface the device can
see.

Failing that, a relay bound to a Windows interface that forwards to the WSL fixture would do the
same job without moving the fixture.

## What is otherwise ready

- builds under the 5.0.5 toolchain (`device-tests/toolchain.sh`, `host_toolchain.txt`);
- harness patch applies cleanly and its probe and bench are generated from the canonical
  `device-tests/harness/` files, so they cannot drift again;
- `tools/instrument_response_stringify.py` instruments the correct site, preserves the
  instrumented file's length, and exports the counter through `commons/basic/Index.ets`;
- expected result once reachable: unfixed `serializes=5` with a 345 KB body per call, fixed
  `serializes=0`.
