// OHMB progress-log counter and bench driver (measurement only)
//
// Declared metric: log_calls_per_pageload. The unfixed page logs on every progress event; the
// fixed page guards at milestones. The guard is the only difference between the variants, so the
// number of events it admits IS the declared count.
//
// The guard is exposed as a callable because the event cannot be synthesised: onProgressChange is
// a Web component event, and a real page load would need a reachable URL. This drives the guard
// directly and says so.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

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
 * The variant's own decision to log. OHM_GUARD_BODY is replaced per variant by
 * tools/instrument_progress_log.py, so the guard is the source under test rather than a copy.
 */
export function ohmProgressLogWouldLog(progress: number): boolean {
  OHM_GUARD_BODY
}

/** Append to ohm-diag.json: the status file is overwritten by the state machine, this is not. */
export function ohmDiag(context: common.UIAbilityContext, label: string, value: string): void {
  try {
    const path = context.filesDir + '/ohm-diag.json';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.APPEND | fs.OpenMode.WRITE_ONLY);
    fs.writeSync(file.fd, '{"t":"' + label + '","v":' + JSON.stringify(value) + '}\n');
    fs.closeSync(file);
  } catch (e) {
  }
}

/** Write the `ready` status and block until the collector touches ohm-go. */
export async function ohmAwaitGo(context: common.UIAbilityContext): Promise<void> {
  const go = context.filesDir + '/ohm-go';
  try {
    if (fs.accessSync(go)) {
      fs.unlinkSync(go);
    }
  } catch (e) {
  }
  ohmTerminalWrite(context, '{"state":"ready"}');
  await new Promise<void>((resolve) => {
    const timer = setInterval(() => {
      try {
        if (fs.accessSync(go)) {
          clearInterval(timer);
          resolve();
        }
      } catch (e) {
      }
    }, 100);
  });
}

/** Write the terminal status the collector waits for. */
export function ohmTerminalWrite(context: common.UIAbilityContext, value: string): void {
  try {
    const file = fs.openSync(context.filesDir + '/ohm-status.json',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.writeSync(file.fd, value);
    fs.closeSync(file);
  } catch (e) {
  }
}
