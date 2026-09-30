import fs from '@ohos.file.fs';
import systemDateTime from '@ohos.systemDateTime';
import hiTraceMeter from '@ohos.hiTraceMeter';
import { common } from '@kit.AbilityKit';

export class OhmProbe {
  static write(context: common.UIAbilityContext, value: string): void {
    const file = fs.openSync(context.filesDir + '/ohm-status.json', fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
    fs.writeSync(file.fd, value);
    fs.closeSync(file);
  }

  static async measure(context: common.UIAbilityContext, name: string,
    prepare: () => Promise<void>, action: () => Promise<number>): Promise<void> {
    try {
      OhmProbe.write(context, '{"state":"preparing"}');
      await prepare();
      const go = context.filesDir + '/ohm-go';
      if (fs.accessSync(go)) fs.unlinkSync(go);
      OhmProbe.write(context, '{"state":"ready"}');
      await new Promise<void>((resolve) => {
        const timer = setInterval(() => {
          if (fs.accessSync(go)) { clearInterval(timer); resolve(); }
        }, 100);
      });
      hiTraceMeter.startTrace('OHMB/' + name, 1);
      const start = systemDateTime.getUptime(systemDateTime.TimeType.STARTUP, true);
      const result = await action();
      const elapsed = (systemDateTime.getUptime(systemDateTime.TimeType.STARTUP, true) - start) / 1000000;
      hiTraceMeter.finishTrace('OHMB/' + name, 1);
      OhmProbe.write(context, '{"state":"done","case":"' + name + '","elapsed_ms":' + elapsed + ',"result":' + result + '}');
    } catch (e) {
      OhmProbe.write(context, '{"state":"error","message":' + JSON.stringify(String(e)) + '}');
    }
  }
}
