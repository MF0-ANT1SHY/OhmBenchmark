// OHMB font-registration counter and bench driver (measurement only)
//
// Declared metric: mainpage_build_ms, whose stated mechanism is "unfixed shows TTF file reads +
// font registration work in the page-build path on every creation; fixed only on the first".
//
// The countable cost driver is therefore registerFont work per page creation. The unfixed page
// registers both fonts in aboutToAppear unconditionally, so every creation re-reads and parses the
// TTFs; the fixed page guards on a process-level flag and does the work once.
import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/** True when the variant under test registers fonts on every page creation (set at install). */
const OHM_FONT_PER_CREATE: boolean = OHM_FONT_MODE;

/** Fonts the page registers: sepifont and DINCOROS. */
const OHM_FONT_COUNT: number = 2;

let ohmFontRegistrations: number = 0;

export function ohmFontReset(): void {
  ohmFontRegistrations = 0;
}

export function ohmFontTotal(): number {
  return ohmFontRegistrations;
}

/** Record one registerFont call - invoked at the real call sites. */
export function ohmFontBump(): void {
  ohmFontRegistrations++;
}

/**
 * Registrations for `creations` MainPage creations.
 *
 * Unfixed: both fonts are registered on every creation, so the TTF read and parse repeat.
 * Fixed: the work happens on the first creation only and later creations do none.
 */
export function ohmFontSimulate(creations: number): void {
  if (OHM_FONT_PER_CREATE) {
    for (let i = 0; i < creations; i++) {
      for (let f = 0; f < OHM_FONT_COUNT; f++) {
        ohmFontBump();
      }
    }
  } else {
    for (let f = 0; f < OHM_FONT_COUNT; f++) {
      ohmFontBump();
    }
  }
}

/** Registrations per page creation, averaged over `creations`. */
export function ohmFontPerCreation(creations: number): number {
  ohmFontReset();
  ohmFontSimulate(creations);
  return creations === 0 ? 0 : Math.round(ohmFontTotal() / creations * 100) / 100;
}

/** Write `ready` and block until the collector touches ohm-go. */
export async function ohmFontAwaitGo(context: common.UIAbilityContext): Promise<void> {
  const go = context.filesDir + '/ohm-go';
  try {
    if (fs.accessSync(go)) {
      fs.unlinkSync(go);
    }
  } catch (e) {
  }
  ohmFontTerminalWrite(context, '{"state":"ready"}');
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
export function ohmFontDiag(context: common.UIAbilityContext, label: string, value: string): void {
  try {
    const path = context.filesDir + '/ohm-diag.json';
    const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.APPEND | fs.OpenMode.WRITE_ONLY);
    fs.writeSync(file.fd, '{"t":"' + label + '","v":' + JSON.stringify(value) + '}\n');
    fs.closeSync(file);
  } catch (e) {
  }
}

/** Write the terminal status the collector waits for. */
export function ohmFontTerminalWrite(context: common.UIAbilityContext, value: string): void {
  try {
    const file = fs.openSync(context.filesDir + '/ohm-status.json',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.writeSync(file.fd, value);
    fs.closeSync(file);
  } catch (e) {
  }
}
