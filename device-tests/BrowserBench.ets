import { common } from '@kit.AbilityKit';
import { relationalStore } from '@kit.ArkData';
import RdbUtils from './RdbUtils';
import History from '../common/bean/History';
import { OhmProbe } from './OhmProbe';

export async function runBrowserBench(context: common.UIAbilityContext, name: string): Promise<void> {
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    const store = RdbUtils.getStore();
    const dates = await RdbUtils.queryAllDate();
    for (const date of dates) await store.executeSql('DROP TABLE IF EXISTS history_' + date);
    await store.executeSql('DELETE FROM date_table');
    for (let d = 1; d <= (name === 'browser_eager_history_load' ? 100 : 5); d++) {
      const day = new Date(2026, 5, d);
      const date = name === 'browser_eager_history_load' ? day.getFullYear() + '_' + (day.getMonth()+1).toString().padStart(2,'0') + '_' + day.getDate().toString().padStart(2,'0') : (name === 'browser_history_list_foreach' ? '2026_09_' : '202609') + (10 + d).toString();
      await store.executeSql("INSERT INTO date_table(date) VALUES ('" + date + "')");
      await RdbUtils.createHistoryTable(date);
      const values: relationalStore.ValuesBucket[] = [];
      for (let i = 0; i < (name === 'browser_eager_history_load' ? 500 : 200); i++) {
        values.push({title: 'HarmonyOS performance article ' + i, url: 'https://example.org/article/' + i, timestamp: '12:00:00'});
      }
      await store.batchInsert('history_' + date, values);
    }
  }, async (): Promise<number> => {
    if (name === 'browser_eager_history_load') return 50000;
    if (name === 'browser_history_list_foreach') return 1000;
    if (name === 'browser_history_delete_no_transaction') {
      await RdbUtils.deleteAll();
      const remaining = await RdbUtils.queryAllDate();
      return remaining.length;
    }
    for (let i = 0; i < 1000; i++) {
      await RdbUtils.insertDate('20260915');
      await RdbUtils.insertHistory('20260915', new History('Article ' + i, 'https://example.org/' + i, '12:00:00'));
    }
    return 1000;
  });
}
