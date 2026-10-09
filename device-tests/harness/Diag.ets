import fs from '@ohos.file.fs';
import { common } from '@kit.AbilityKit';

/**
 * Append-only diagnostic log, separate from `ohm-status.json`.
 *
 * The status file is overwritten by the state machine (`ready`, then `done`), so a diagnostic
 * written into it during `prepare()` is destroyed within milliseconds. That is exactly what
 * happened when the bench tried to report what the history page saw, and it left the
 * parse-counter reading of 0 ambiguous between "the page never built its rows" and "the bench
 * read a different module instance than the page writes".
 *
 * This file is only ever appended to, so every checkpoint survives until it is read.
 */
export class Diag {
  static log(context: common.UIAbilityContext, label: string, value: string): void {
    try {
      const path = context.filesDir + '/ohm-diag.json';
      const line = '{"t":"' + label + '","v":' + JSON.stringify(value) + '}\n';
      const file = fs.openSync(path, fs.OpenMode.CREATE | fs.OpenMode.APPEND | fs.OpenMode.WRITE_ONLY);
      fs.writeSync(file.fd, line);
      fs.closeSync(file);
    } catch (e) {
      // diagnostics must never break the measurement
    }
  }
}
