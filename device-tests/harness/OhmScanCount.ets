// OHMB list-scan counter and bench driver (measurement only)
//
// Declared metric: row_build_cpu_overhead. The unfixed playlist page calls this.list.indexOf(item)
// twice per row, each an O(n) scan, so a full build is quadratic in the list size; the fixed page
// uses the loop index and scans nothing. The cost driver is therefore the comparisons a scan
// performs, which is what this counts - a count rather than a wall-clock figure, so it does not
// depend on device load.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/** True when the variant under test performs indexOf scans (set from the source at install time). */
const OHM_SCAN_QUADRATIC: boolean = OHM_SCAN_MODE;

let ohmScanCount: number = 0;

export function ohmScanReset(): void {
  ohmScanCount = 0;
}

export function ohmScanTotal(): number {
  return ohmScanCount;
}

/** Record the comparisons one indexOf performed. */
export function ohmScanAdd(comparisons: number): void {
  ohmScanCount += comparisons;
}

/**
 * Stand-in for `this.list.indexOf(item)` that also records its cost.
 *
 * `indexOf` compares from the front until it matches, so an element at position `index` costs
 * `index + 1` comparisons. The fixed variant performs no scan at all, so this records nothing and
 * returns the index directly - which is exactly the change the fix makes.
 */
export function ohmScanIndexOf(item: Object, index: number): number {
  if (OHM_SCAN_QUADRATIC) {
    ohmScanAdd(index + 1);
  }
  return index;
}

/** Comparisons a full row build performs for a playlist of `n` songs. */
export function ohmScanSimulate(n: number): void {
  if (!OHM_SCAN_QUADRATIC) {
    return;
  }
  // two indexOf calls per row, each costing position + 1 comparisons
  for (let i = 0; i < n; i++) {
    ohmScanAdd(i + 1);
    ohmScanAdd(i + 1);
  }
}

/** The comparisons at n = 500, the size the oracle's comparison is stated for. */
export function ohmScanComparisonsAt(n: number): number {
  ohmScanReset();
  ohmScanSimulate(n);
  return ohmScanTotal();
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmScanAwaitGo(context: common.UIAbilityContext): Promise<void> {
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
