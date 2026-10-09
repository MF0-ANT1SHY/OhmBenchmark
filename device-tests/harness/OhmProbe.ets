import fs from '@ohos.file.fs';
import systemDateTime from '@ohos.systemDateTime';
import hiTraceMeter from '@ohos.hiTraceMeter';
import { common } from '@kit.AbilityKit';

/**
 * Device measurement harness shared by the ytmusic cases.
 *
 * The bench entry runs inside the app, prepares a deterministic fixture, signals
 * `state=ready`, waits for the host to touch `ohm-go` (so profiling starts before the region
 * of interest), performs the measured action, then reports `state=done` with the elapsed time
 * and a result value.
 *
 * Counters for a case's declared oracle are emitted as `OHMB/<Name>` trace markers, the same
 * mechanism tools/device/analyze.py reads for the other hosts.
 */
export class OhmProbe {
  static write(context: common.UIAbilityContext, value: string): void {
    const file = fs.openSync(context.filesDir + '/ohm-status.json',
      fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY | fs.OpenMode.TRUNC);
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
      OhmProbe.write(context, '{"state":"done","case":"' + name + '","elapsed_ms":' + elapsed +
        ',"result":' + result + '}');
    } catch (e) {
      OhmProbe.write(context, '{"state":"error","message":' + JSON.stringify(String(e)) + '}');
    }
  }
}

/** Counters for the declared oracles, one per case, emitted as trace markers. */
export class OhmCounters {
  // ytmusic_history_json_parse_per_row: history_page_render_cpu_ms
  static jsonParses: number = 0;
  // ytmusic_search_no_debounce: search_requests_per_query
  static searchRequests: number = 0;
  // ytmusic_current_playing_timeupdate: player_page_updates_per_minute
  static playerUpdates: number = 0;

  static reset(): void {
    OhmCounters.jsonParses = 0;
    OhmCounters.searchRequests = 0;
    OhmCounters.playerUpdates = 0;
  }

  static emit(): void {
    hiTraceMeter.traceByValue('OHMB/JsonParseCount', OhmCounters.jsonParses);
    hiTraceMeter.traceByValue('OHMB/SearchRequestCount', OhmCounters.searchRequests);
    hiTraceMeter.traceByValue('OHMB/PlayerUpdateCount', OhmCounters.playerUpdates);
  }
}
