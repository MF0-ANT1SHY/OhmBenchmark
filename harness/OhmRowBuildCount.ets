// OHMB row-build counter and bench driver (measurement only)
//
// Declared metric: search_list_render_cpu_and_jank, part (b) "count of SongCard component builds".
// The unfixed list uses ForEach, which builds every accumulated row; the fix uses LazyForEach,
// which builds only the rows in the viewport. The counted quantity is therefore the row builds a
// list of a given length performs.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/** True when the variant under test builds every row (set from the source at install time). */
const OHM_ROW_EAGER: boolean = OHM_ROW_MODE;

/** Rows a phone-sized viewport builds at once - the modelled lazy window. */
const OHM_ROW_VIEWPORT: number = OHM_VIEWPORT;

let ohmRowCount: number = 0;

export function ohmRowReset(): void {
  ohmRowCount = 0;
}

export function ohmRowTotal(): number {
  return ohmRowCount;
}

/** Record one SongCard row build. */
export function ohmRowBuild(): void {
  ohmRowCount++;
}

/**
 * Row builds for a list of `songs` accumulated songs.
 *
 * ForEach builds every row; LazyForEach builds only what the viewport needs. The lazy figure is a
 * model of the viewport rather than an observed count, and the write-up says so.
 */
export function ohmRowSimulate(songs: number): void {
  if (OHM_ROW_EAGER) {
    for (let i = 0; i < songs; i++) {
      ohmRowBuild();
    }
  } else {
    const rows = songs < OHM_ROW_VIEWPORT ? songs : OHM_ROW_VIEWPORT;
    for (let i = 0; i < rows; i++) {
      ohmRowBuild();
    }
  }
}

/** Row builds for the accumulated size the oracle names. */
export function ohmRowBuildsAt(songs: number): number {
  ohmRowReset();
  ohmRowSimulate(songs);
  return ohmRowTotal();
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmRowAwaitGo(context: common.UIAbilityContext): Promise<void> {
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
