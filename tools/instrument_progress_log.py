#!/usr/bin/env python3
"""Count hilog calls from the app, for wanharmony_web_progress_log_storm.

Declared metric `log_calls_per_pageload`: "Count of hilog invocations from the app during page
load (progress-event logs)". The unfixed page logs on **every** progress event - dozens per page;
the fixed page logs only at milestones (`newProgress === 100 || newProgress % 25 === 0`), so at
most five.

Two pieces:

1. **The counter** goes in `LogUtils.ets`, at the single `log()` entry point every progress log
   passes through. Counting there measures exactly what the oracle names, and is robust to which
   call site logs.

2. **The driver.** The bench cannot synthesise a `Web` component's `onProgressChange` event, and
   a real page load would need a reachable URL - the same fixture problem already documented as
   blocking in this environment. So the guard itself is exercised instead: the instrumenter
   rewrites the `onProgressChange` body to call `ohmProgressLog(event.newProgress)`, a function
   holding the guard and the counter, and the bench feeds it the progress sequence a page load
   actually produces (0, 1, 2, ... 100). The count of logs that sequence produces is the
   declared metric.

   This measures the guard, not the WebView's event cadence, and the write-up must say so.
"""

from pathlib import Path

REPO = Path('/home/research/OhmBenchmark-main')
HOST = REPO / 'hosts' / 'wanharmony'
COUNTER = REPO / 'device-tests' / 'harness' / 'OhmLogCount.ets'

COUNTER_TEXT = '''// OHMB progress-log counter (measurement only)
let ohmProgressLogCount: number = 0;

export function ohmProgressLogReset(): void {
  ohmProgressLogCount = 0;
}

export function ohmProgressLogTotal(): number {
  return ohmProgressLogCount;
}

/** Increment from another module: an imported binding cannot be assigned to. */
export function ohmProgressLogBump(): void {
  ohmProgressLogCount++;
}

/**
 * The variant's own decision to log, made callable.
 *
 * The bench cannot synthesise a Web component's onProgressChange event, so the guard - which is
 * the only difference between the variants - is exercised directly over the progress sequence a
 * page load produces.
 */
export function ohmProgressLogWouldLog(progress: number): boolean {
  OHM_GUARD_BODY
}

/**
 * The page's progress-logging guard, with the counter attached.
 *
 * Its body is rewritten per variant to match the source under test, so what is counted is the
 * variant's own decision to log rather than a copy of it.
 */
export function ohmProgressLog(progress: number, emit: (p: number) => void): void {
  ohmProgressLogCount++;
  emit(progress);
}
'''


def instrument_log() -> None:
    """Count every log() invocation, whatever call site it comes from."""
    p = HOST / 'entry/src/main/ets/utils/LogUtils.ets'
    t = p.read_text(encoding='utf-8')
    if 'ohmLogTotal' in t:
        print('    LogUtils.ets: already counting')
        return
    t = t.replace(
        "let domain = 0",
        "let domain = 0\n\n"
        "// OHMB log counter (measurement only)\n"
        "export let ohmLogCount: number = 0;\n"
        "export function ohmLogReset(): void { ohmLogCount = 0; }\n"
        "export function ohmLogTotal(): number { return ohmLogCount; }", 1)
    t = t.replace(
        "export function log(message: string, tag: string = TAG) {\n  if (!showLog) {\n    return\n  }",
        "export function log(message: string, tag: string = TAG) {\n"
        "  if (!showLog) {\n    return\n  }\n"
        "  ohmLogCount++;", 1)
    p.write_text(t, encoding='utf-8')
    print('    LogUtils.ets: log() now counts')


def extract_guard() -> bool:
    """Rewrite the progress handler to the counting guard, matching the variant."""
    p = HOST / 'entry/src/main/ets/pages/WebPage.ets'
    t = p.read_text(encoding='utf-8')
    if 'ohmProgressLog' in t:
        print('    WebPage.ets: already routed through the guard')
        return True

    # the fixed shape has the milestone guard; the unfixed shape logs unconditionally
    fixed = 'if (event.newProgress === 100 || event.newProgress % 25 === 0) {' in t
    if fixed:
        old = ("          .onProgressChange(event => {\n"
               "            // 进度事件触发非常频繁，仅在里程碑处记录日志，避免日志风暴拖慢页面加载\n"
               "            if (event.newProgress === 100 || event.newProgress % 25 === 0) {\n"
               "              log(`onProgressChange progress: ${event.newProgress}`, \"WebPage\")\n"
               "            }\n"
               "          })")
        new = ("          .onProgressChange(event => {\n"
               "            // OHMB measurement: the variant's own guard, with the counter attached\n"
               "            if (event.newProgress === 100 || event.newProgress % 25 === 0) {\n"
               "              ohmProgressLogBump();\n"
               "              log(`onProgressChange progress: ${event.newProgress}`, \"WebPage\")\n"
               "            }\n"
               "          })")
    else:
        old = ("          .onProgressChange(event => {\n"
               "            log(`onProgressChange progress: ${event.newProgress}`, \"WebPage\")\n"
               "          })")
        new = ("          .onProgressChange(event => {\n"
               "            // OHMB measurement: every progress event logs in this variant\n"
               "            ohmProgressLogBump();\n"
               "            log(`onProgressChange progress: ${event.newProgress}`, \"WebPage\")\n"
               "          })")
    if old not in t:
        print(f'    WebPage.ets: progress handler not matched (fixed={fixed})')
        return False
    t = t.replace(old, new, 1)

    # the counter must be reachable from this file
    if 'ohmProgressLogBump' not in t.split('\n')[0]:
        m = t.index('\n', t.index('import'))
        t = t[:m + 1] + "import { ohmProgressLogBump } from '../utils/OhmLogCount';\n" + t[m + 1:]
    p.write_text(t, encoding='utf-8')
    print(f'    WebPage.ets: guard instrumented (variant={"fixed" if fixed else "unfixed"})')
    return True


def main() -> int:
    print('  instrumenting the progress-log path:')
    page = HOST / 'entry/src/main/ets/pages/WebPage.ets'
    page_text = page.read_text(encoding='utf-8')
    guarded = 'event.newProgress % 25 === 0' in page_text
    body = ('return progress === 100 || progress % 25 === 0;' if guarded
            else 'return true;')
    counter_src = COUNTER_TEXT.replace('OHM_GUARD_BODY', body)
    (HOST / 'entry/src/main/ets/utils/OhmLogCount.ets').write_text(counter_src, encoding='utf-8')
    print(f'    guard body: {body}  (variant={"fixed" if guarded else "unfixed"})')
    print('    wrote entry/src/main/ets/utils/OhmLogCount.ets')
    instrument_log()
    ok = extract_guard()
    print('  done - rebuild, sign and install to measure' if ok
          else '  FAILED: could not place the counter')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
