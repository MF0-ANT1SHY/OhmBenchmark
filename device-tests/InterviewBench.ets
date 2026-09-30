import { common } from '@kit.AbilityKit';
import { historyStore } from './history';
import { hdHttp } from '@itcast/basic';
import { OhmProbe } from './OhmProbe';

interface FixtureRow { id: number; title: string; description: string; }
export async function runInterviewBench(context: common.UIAbilityContext, name: string): Promise<void> {
  await OhmProbe.measure(context, name, async (): Promise<void> => {
    if (name === 'interviewapp_response_log_full_stringify') {
      hdHttp.baseURL = 'http://127.0.0.1:18766/';
      return;
    }
    historyStore.clear();
    if (name === 'interviewapp_search_history_unbounded') {
      for (let i=0;i<5000;i++) historyStore.setItem('HarmonyOS interview question '+i);
    }
    await new Promise<void>((resolve) => { setTimeout(resolve, 2500); });
  }, async (): Promise<number> => {
    if (name === 'interviewapp_search_history_unbounded') {
      let total=0;
      for (let i=0;i<100;i++) total+=historyStore.getAll().length;
      return total;
    }
    if (name === 'interviewapp_response_log_full_stringify') {
      let total=0;
      for (let i=0;i<5;i++) {
        const response = await hdHttp.get<FixtureRow[]>('response');
        total+=response.data.length;
      }
      return total;
    }
    for (let i=0;i<1000;i++) historyStore.setItem('HarmonyOS interview question '+i);
    // Include the application's own deferred flush (2 seconds) in both windows.
    await new Promise<void>((resolve) => { setTimeout(resolve, 3000); });
    return historyStore.getAll().length;
  });
}
