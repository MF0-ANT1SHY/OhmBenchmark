// OHMB persistence-write counter and bench driver (measurement only)
//
// Declared metric: persistent_write_bytes_per_loadmore. The unfixed page makes the whole growing
// home list persistent, so every load-more serialises the entire accumulated array and the total
// write volume is quadratic in pages; the fixed page persists a separate first-page snapshot and
// writes it once.
//
// The serialised size is measured with JSON.stringify - the same serialisation the persistence
// layer performs - so the byte figures are real rather than per-item constants assumed by hand.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/** True when the variant under test persists the growing list (set from the source at install). */
const OHM_PERSIST_GROWING: boolean = OHM_PERSIST_MODE;

let ohmPersistBytes: number = 0;
let ohmPersistFirst: number = 0;
let ohmPersistLast: number = 0;
let ohmPersistCycles: string[] = [];

/** Roughly the shape of one home-list article, matching what the app stores. */
class OhmArticle {
  id: number = 0;
  title: string = '';
  link: string = '';
  author: string = '';
  chapterName: string = '';
  niceDate: string = '';
  constructor(i: number) {
    this.id = i;
    this.title = 'HarmonyOS engineering article ' + i;
    this.link = 'https://example.org/article/' + i;
    this.author = 'author' + (i % 20);
    this.chapterName = 'Chapter ' + (i % 10);
    this.niceDate = '2026/09/30 12:00:00';
  }
}

export function ohmPersistReset(): void {
  ohmPersistBytes = 0;
  ohmPersistFirst = 0;
  ohmPersistLast = 0;
  ohmPersistCycles = [];
}

/** Bytes the persistence layer writes for a list of `n` articles. */
export function ohmPersistBytesFor(n: number): number {
  const list: OhmArticle[] = [];
  for (let i = 0; i < n; i++) {
    list.push(new OhmArticle(i));
  }
  return JSON.stringify(list).length;
}

/**
 * Simulate `pages` load-more cycles of `perPage` articles each, accumulating the bytes each cycle
 * would write.
 *
 * Unfixed: the list is persistent, so every assignment serialises the whole accumulated array.
 * Fixed: only the first page is persisted, so the later cycles write nothing.
 */
export function ohmPersistRun(perPage: number, pages: number): void {
  for (let p = 1; p <= pages; p++) {
    const accumulated = perPage * p;
    let written = 0;
    if (OHM_PERSIST_GROWING || p === 1) {
      written = ohmPersistBytesFor(accumulated);
    }
    ohmPersistBytes += written;
    ohmPersistCycles.push(String(written));
    if (p === 1) {
      ohmPersistFirst = written;
    }
    ohmPersistLast = written;
  }
}

export function ohmPersistTotal(): number {
  return ohmPersistBytes;
}

export function ohmPersistPerCycleFirst(): number {
  return ohmPersistFirst;
}

export function ohmPersistPerCycleLast(): number {
  return ohmPersistLast;
}

export function ohmPersistPerCycleLine(): string {
  return ohmPersistCycles.join(',');
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmPersistAwaitGo(context: common.UIAbilityContext): Promise<void> {
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
