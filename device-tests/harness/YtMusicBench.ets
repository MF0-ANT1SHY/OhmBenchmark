import { common } from '@kit.AbilityKit';
import { router } from '@kit.ArkUI';
import { OhmProbe, OhmCounters } from './OhmProbe';
// the instrumented page exposes its running parse total; reading it here avoids
// a cycle, since History.ets must not import the bench back
import { ohmParseTotal } from '../pages/History';

/**
 * Bench entry for the ytmusic cases.
 *
 * ytmusic_history_json_parse_per_row - counts JSON.parse calls made by the history page while
 * it builds its list. The page reads its entries from the AppStorage key `history` and parses
 * each entry's JSON per property access inside ForEach; the fixed page parses once per entry.
 *
 * The counter is emitted *after* the render, and the instrumented helper keeps a running total
 * rather than a per-measurement one, because ForEach runs on the UI thread during the page
 * transition - by the time this async function resumes, the parses have already happened.
 */
const FIXTURE_ROWS = 200;

function makeEntry(i: number): string {
  return JSON.stringify({ img: 'cover/' + i + '.png', name: 'Track ' + i, creator: 'Artist ' + i });
}

export async function runYtMusicBench(context: common.UIAbilityContext, name: string): Promise<void> {
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    OhmCounters.reset();
    if (name === 'ytmusic_history_json_parse_per_row') {
      const rows = new Set<string>();
      for (let i = 0; i < FIXTURE_ROWS; i++) {
        rows.add(makeEntry(i));
      }
      AppStorage.setOrCreate('history', rows);
      const seen = AppStorage.get<Set<string>>('history');
      OhmProbe.write(context, '{"state":"preparing","seeded":' + rows.size +
        ',"seenBack":' + (seen ? seen.size : -1) + '}');
    }
    return;
  }, async (): Promise<number> => {
    if (name === 'ytmusic_history_json_parse_per_row') {
      // Drive the page under test: route to it so its own ForEach builds the rows. The parses
      // the page performs are what the oracle counts.
      let routed = 'ok';
      try {
        router.pushUrl({ url: 'pages/History' });
      } catch (e) {
        routed = 'threw:' + String(e);
      }
      await new Promise<void>((resolve) => { setTimeout(resolve, 2500); });
      // the page parsed on the UI thread; read its own running total
      const total = ohmParseTotal();
      const seenAfter = AppStorage.get<Set<string>>('history');
      OhmProbe.write(context, '{"state":"preparing","routed":"' + routed +
        '","parseTotal":' + total + ',"rowsVisible":' + (seenAfter ? seenAfter.size : -1) + '}');
      OhmCounters.emit();
      return total;
    }
    OhmCounters.emit();
    return 0;
  });
}
