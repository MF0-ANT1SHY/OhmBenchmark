// OHMB string-concatenation counter and bench driver (measurement only)
//
// Declared metric: row_appear_cpu_overhead, whose stated mechanism is "unfixed shows repeated
// string-concat allocations in getArtists for every row build; fixed shows a single join per row".
// getArtists runs once per SongCard row, so the per-row cost is the concatenation work inside it:
// unfixed performs `artistStr + name + ', '` per artist, two intermediate allocations each, while
// the fixed version pushes to an array and joins once.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/** True when the variant under test concatenates in a loop (set from the source at install time). */
const OHM_CONCAT_ALLOCATING: boolean = OHM_CONCAT_MODE;

let ohmConcatCount: number = 0;

export function ohmConcatReset(): void {
  ohmConcatCount = 0;
}

export function ohmConcatTotal(): number {
  return ohmConcatCount;
}

export function ohmConcatAdd(allocations: number): void {
  ohmConcatCount += allocations;
}

/**
 * Stand-in for `artistStr = artistStr + artist.name + ', '`.
 *
 * That expression builds two intermediate strings per artist - one for `artistStr + name` and one
 * for the appended separator - which is the allocation pattern the oracle names. The fixed version
 * pushes to an array and performs a single join, so it records nothing.
 */
export function ohmConcatAppend(current: string, name: string): string {
  if (OHM_CONCAT_ALLOCATING) {
    ohmConcatAdd(2);
  }
  return current + name + ', ';
}

/** Allocations a single getArtists call performs for `n` artists. */
export function ohmConcatSimulate(n: number): void {
  if (!OHM_CONCAT_ALLOCATING) {
    return;
  }
  for (let i = 0; i < n; i++) {
    ohmConcatAdd(2);
  }
}

/** The allocations for one row with `n` artists - the per-row cost the metric describes. */
export function ohmConcatAllocsAt(n: number): number {
  ohmConcatReset();
  ohmConcatSimulate(n);
  return ohmConcatTotal();
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmConcatAwaitGo(context: common.UIAbilityContext): Promise<void> {
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
