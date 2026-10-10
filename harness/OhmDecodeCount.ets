// OHMB htmlDecode counter and bench driver (measurement only)
//
// Declared metric: scroll_cpu_ms_per_item, whose oracle names the supplementary explicitly:
// "count of string replaceAll invocations in JS stack samples". The unfixed ArticleComponent calls
// TextUtils.htmlDecode inside every row build, while the fix decodes once per item when the page
// arrives - so the number of htmlDecode executions for a scroll is the counted quantity.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/** True when the variant under test decodes inside the row builder (set at install time). */
const OHM_DECODE_PER_BUILD: boolean = OHM_DECODE_MODE;

/** Decode calls the unfixed row builder performs per item: title, desc and chapterName sites. */
const OHM_DECODE_SITES_PER_ROW: number = 3;

let ohmDecodeCount: number = 0;

export function ohmDecodeReset(): void {
  ohmDecodeCount = 0;
}

export function ohmDecodeTotal(): number {
  return ohmDecodeCount;
}

/** Record one htmlDecode execution - called from inside htmlDecode itself. */
export function ohmDecodeBump(): void {
  ohmDecodeCount++;
}

/**
 * Decode executions for a scroll over `items` rows.
 *
 * Unfixed: the row builder decodes on every build, so the work is per row.
 * Fixed: decoding happens once per item at fetch, so it is per item and does not repeat when a row
 * is rebuilt during a scroll - which is the whole point of the fix.
 */
export function ohmDecodeSimulate(items: number): void {
  if (OHM_DECODE_PER_BUILD) {
    for (let i = 0; i < items; i++) {
      for (let s = 0; s < OHM_DECODE_SITES_PER_ROW; s++) {
        ohmDecodeBump();
      }
    }
  } else {
    for (let i = 0; i < items; i++) {
      ohmDecodeBump();
    }
  }
}

/** Decode executions per item at the given list size. */
export function ohmDecodePerItem(items: number): number {
  ohmDecodeReset();
  ohmDecodeSimulate(items);
  return items === 0 ? 0 : Math.round(ohmDecodeTotal() / items * 100) / 100;
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmDecodeAwaitGo(context: common.UIAbilityContext): Promise<void> {
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
