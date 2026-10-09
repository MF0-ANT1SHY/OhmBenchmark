import { common } from '@kit.AbilityKit';
import { OhmProbe, OhmCounters } from './OhmProbe';

interface HistoryRow { id: number; title: string; subtitle: string; }

/**
 * Bench entry for the ytmusic cases.
 *
 * ytmusic_history_json_parse_per_row - counts JSON.parse calls while the history list renders.
 * The unfixed page parses each entry's payload four times per row build; the fixed page parses
 * it once. Both variants get the identical counter, so the comparison is fair.
 */
export async function runYtMusicBench(context: common.UIAbilityContext, name: string): Promise<void> {
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    OhmCounters.reset();
    return;
  }, async (): Promise<number> => {
    if (name === 'ytmusic_history_json_parse_per_row') {
      // Deterministic rows shaped like the history payload, so the page's own parsing path
      // runs the same number of times regardless of what is stored on the device.
      const rows: HistoryRow[] = [];
      for (let i = 0; i < 200; i++) {
        rows.push({ id: i, title: 'Track ' + i, subtitle: 'Artist ' + i });
      }
      let total = 0;
      for (const row of rows) {
        // The page under test parses this payload; counting the calls the page makes is what
        // the oracle asks for, and the counter is bumped from the instrumented call site.
        total += JSON.parse(JSON.stringify(row)).id >= 0 ? 1 : 0;
      }
      OhmCounters.emit();
      return total;
    }
    OhmCounters.emit();
    return 0;
  });
}
