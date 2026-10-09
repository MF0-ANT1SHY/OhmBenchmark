// OHMB player-update counter and bench driver (measurement only)
//
// Declared metric: player_page_updates_per_minute. The unfixed handler assigns its state on every
// timeUpdate (~10/s, so ~600/minute); the fixed handler guards on the displayed second (~60/minute).
// The guard is the only difference, so the writes it admits ARE the declared count.
//
// The guard is exposed as a callable because timeUpdate cannot be synthesised and a real minute of
// playback would dominate a run. Committing each admitted second matters: without it the fixed
// variant would compare every tick against the initial value and admit all of them, making the two
// variants indistinguishable - a trap this repository already hit on the cloudmusic sibling.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/** True when the variant under test guards on the displayed second (set from the source). */
const OHM_UPDATE_GUARDED: boolean = OHM_UPDATE_MODE;

let ohmUpdateCount: number = 0;
let ohmUpdateLastSecond: number = -1;

export function ohmUpdateReset(): void {
  ohmUpdateCount = 0;
  ohmUpdateLastSecond = -1;
}

export function ohmUpdateBump(): void {
  ohmUpdateCount++;
}

export function ohmUpdateTotal(): number {
  return ohmUpdateCount;
}

/** Record an admitted second, mirroring the source's `lastReportedSecond = second`. */
export function ohmUpdateCommit(second: number): void {
  ohmUpdateLastSecond = second;
}

/** The variant's own decision to write: unconditional, or only when the second changes. */
export function ohmUpdateWouldWrite(timeMs: number): boolean {
  if (!OHM_UPDATE_GUARDED) {
    return true;
  }
  return Math.floor(timeMs / 1000) !== ohmUpdateLastSecond;
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmUpdateAwaitGo(context: common.UIAbilityContext): Promise<void> {
  const go = context.filesDir + '/ohm-go';
  try {
    if (fs.accessSync(go)) {
      fs.unlinkSync(go);
    }
  } catch (e) {
  }
  ohmUpdateTerminalWrite(context, '{"state":"ready"}');
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
export function ohmUpdateDiag(context: common.UIAbilityContext, label: string, value: string): void {
  try {
    const path = context.filesDir + '/ohm-diag.json';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.APPEND | fs.OpenMode.WRITE_ONLY);
    fs.writeSync(file.fd, '{"t":"' + label + '","v":' + JSON.stringify(value) + '}\n');
    fs.closeSync(file);
  } catch (e) {
  }
}

/** Write the terminal status the collector waits for. */
export function ohmUpdateTerminalWrite(context: common.UIAbilityContext, value: string): void {
  try {
    const file = fs.openSync(context.filesDir + '/ohm-status.json',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.writeSync(file.fd, value);
    fs.closeSync(file);
  } catch (e) {
  }
}

/**
 * Measure player-page state updates for the tick sequence one minute of idle playback produces.
 *
 * `timeUpdate` fires about every 100ms, so 600 ticks span 60s. The same-second guard is the only
 * difference between the variants, so the writes it admits are the declared
 * `player_page_updates_per_minute`. Called from the host's bench, which dispatches on case name.
 */
export function ohmRunPlayerUpdateBench(): number {
  ohmUpdateReset();
  let writes = 0;
  for (let tick = 0; tick < 600; tick++) {
    const ms = tick * 100;
    if (ohmUpdateWouldWrite(ms)) {
      writes++;
      ohmUpdateBump();
      // committing each admitted second is essential: without it the guarded variant would compare
      // every tick against the initial value and admit all of them
      ohmUpdateCommit(Math.floor(ms / 1000));
    }
  }
  return writes;
}
