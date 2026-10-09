// OHMB PLAY_TIME write counter and bench driver (measurement only)
//
// Declared metric: player_page_rerenders_per_minute. Unfixed writes the global PLAY_TIME on every
// timeUpdate (~10/s, so ~600/minute); the fixed build guards on the displayed second (~60/minute).
// The guard is the only difference, so the writes it admits ARE the declared count.
//
// The guard is exposed as a callable because timeUpdate cannot be synthesised and a real minute of
// playback would dominate a run. This drives the guard over the tick sequence a minute produces and
// says so in the write-up.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

let ohmPlayWriteCount: number = 0;
let ohmPlayLastReported: number = -1;

export function ohmPlayReset(): void {
  ohmPlayWriteCount = 0;
  ohmPlayLastReported = -1;
}

export function ohmPlayBump(): void {
  ohmPlayWriteCount++;
}

export function ohmPlayTotal(): number {
  return ohmPlayWriteCount;
}

/** The last second the guard admitted, so the fixed variant's state persists across calls. */
export function ohmPlayLastSecond(): number {
  return ohmPlayLastReported;
}

/**
 * Record an admitted second. The source assigns `lastReportedSecond = second` inside the guard,
 * and without the matching assignment here the fixed variant would compare every tick against the
 * initial value and admit all of them, making the two variants indistinguishable.
 */
export function ohmPlayCommit(second: number): void {
  ohmPlayLastReported = second;
}

/**
 * The variant's own decision to write PLAY_TIME. OHM_GUARD_BODY is replaced per variant from the
 * source under test, so the guard is not a copy of it.
 */
export function ohmPlayWouldWrite(timeMs: number): boolean {
  OHM_GUARD_BODY
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmPlayAwaitGo(context: common.UIAbilityContext): Promise<void> {
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
