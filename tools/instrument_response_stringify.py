#!/usr/bin/env python3
"""Count full-response serializations on HTTP response paths, and report them.

`interviewapp_response_log_full_stringify` declares `response_handler_cpu_ms`: CPU time in the
HTTP response handling path per API call. The unfixed handler logs
`JSON.stringify(res.result).substring(0, 200)`, serializing the entire body to keep 200
characters; the fixed handler logs two fields.

The oracle's own comparison states the cost driver: "unfixed serializes each full response body
(O(payload)); fixed logs O(1) fields". The local fixture returns a 345 KB body with 1000 rows, so
each serialization is expensive. The counter records how many occur.

Where the pieces live, and why:

  commons/basic/.../OhmResponseCount.ets  counter state plus an append-only diag writer
  commons/basic/.../request.ets           imports the counter by relative path (same module)
  features/home/.../InterviewBench.ets    imports it as '@itcast/basic', which it already uses

The counter cannot live in features/home: commons/basic importing from home would be circular,
and ArkTS rejected '@itcast/home' from that direction.

Idempotent; reports when the fixed shape has nothing left to count.

Usage: python3 tools/instrument_response_stringify.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COUNTER_MODULE = 'commons/basic/src/main/ets/utils/OhmResponseCount.ets'
COUNTER_PACKAGE = './OhmResponseCount'

# Where the fixture lives. The default assumes the device can reach its own loopback
# through an hdc forward; set --fixture-host when it cannot (for example when the
# fixture runs in WSL and the device is a physical phone on Windows).
DEFAULT_FIXTURE_HOST = '127.0.0.1'

COUNTER_TEXT = '// OHMB response-stringify counter (measurement only)\nimport fs from \'@ohos.file.fs\';\nimport { common } from \'@kit.AbilityKit\';\n\nexport let ohmResponseStringifyCount: number = 0;\n\nexport function ohmResponseStringifyReset(): void {\n  ohmResponseStringifyCount = 0;\n}\n\nexport function ohmResponseStringifyTotal(): number {\n  return ohmResponseStringifyCount;\n}\n\nexport function ohmResponseStringify(value: Object): string {\n  ohmResponseStringifyCount++;\n  return JSON.stringify(value);\n}\n\n/** Append a checkpoint to ohm-diag.json: the status file overwrites, this does not. */\nexport function ohmDiag(context: common.UIAbilityContext, label: string, value: string): void {\n  try {\n    const path = context.filesDir + \'/ohm-diag.json\';\n    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.APPEND | fs.OpenMode.WRITE_ONLY);\n    fs.writeSync(file.fd, \'{"t":"\' + label + \'","v":\' + JSON.stringify(value) + \'}\\n\');\n    fs.closeSync(file);\n  } catch (e) {\n    // diagnostics must never break the measurement\n  }\n}\n'


def instrument(request_file: Path) -> int:
    t = request_file.read_text(encoding='utf-8')
    before = t
    if 'ohmResponseStringify(' in t:
        print(f'    {request_file.name}: already instrumented')
        return 0

    t, n = re.subn(r'JSON\.stringify\(res\.result\)', 'ohmResponseStringify(res.result)', t)
    if n == 0:
        print(f'    {request_file.name}: no full-body serialization on this path '
              f'(the fixed shape); counting 0 is correct')
        return 0

    m = re.search(r'^(import .*\n)', t, re.M)
    if not m:
        raise SystemExit(f'  FAILED: no imports found in {request_file}')
    # INSERT the import; the rest of the file must survive. Losing the tail here once
    # truncated request.ets to two lines and broke every consumer of the package.
    t = t[:m.end()] + f"import {{ ohmResponseStringify }} from '{COUNTER_PACKAGE}';\n" + t[m.end():]

    added = len(t.splitlines()) - len(before.splitlines())
    if added < 1 or len(t.splitlines()) < len(before.splitlines()):
        raise SystemExit(
            f'  FAILED: instrumentation would lose code in {request_file.name} '
            f'({len(before.splitlines())} lines -> {len(t.splitlines())}). Refusing to write.')
    request_file.write_text(t, encoding='utf-8')
    print(f'    {request_file.name}: routed {n} full-body serialization(s) through the counter')
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    ap.add_argument('--fixture-host', default=DEFAULT_FIXTURE_HOST,
                    help='host the bench should send fixture requests to')
    a = ap.parse_args()
    root = Path(a.hosts) / 'interviewapp'
    cands = [c for c in root.glob('**/request.ets') if 'oh_modules' not in str(c)]
    if not cands:
        raise SystemExit('  FAILED: cannot find request.ets in the interviewapp host')
    print('  instrumenting the HTTP response path:')
    mod = root / COUNTER_MODULE
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text(COUNTER_TEXT, encoding='utf-8')
    print(f'    wrote {mod.relative_to(root)}')

    # the bench's own module needs the constant it now references
    const = root / 'features/home/src/main/ets/utils/OhmFixtureHost.ets'
    const.write_text(
        '// OHMB fixture host (measurement only)\n'
        f"export const OHM_FIXTURE_HOST: string = '{a.fixture_host}';\n", encoding='utf-8')
    print(f'    wrote {const.relative_to(root)} (fixture host {a.fixture_host})')
    n = instrument(cands[0])

    # publish the counter through the package index: consumers import '@itcast/basic', and a
    # new file under the package is not part of that surface on its own
    index = root / 'commons/basic/Index.ets'
    if index.exists():
        it = index.read_text(encoding='utf-8')
        line = ("export { ohmResponseStringifyReset, ohmResponseStringifyTotal, ohmDiag }"
                " from './src/main/ets/utils/OhmResponseCount';\n")
        if 'OhmResponseCount' not in it:
            index.write_text(it.rstrip('\n') + '\n' + line, encoding='utf-8')
            print(f'    {index.relative_to(root)}: counter exported from the package index')
        else:
            print(f'    {index.relative_to(root)}: counter already exported')
    else:
        print(f'    WARNING: no package index at {index}; consumers cannot import the counter')

    print(f'  done - {n} site(s) counted; rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
