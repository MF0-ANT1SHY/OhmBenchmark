import { common } from '@kit.AbilityKit';
import getWeatherUtil from '../viewmodel/getWeatherUtil';
import { OhmProbe } from './OhmProbe';
export async function runWeatherBench(context: common.UIAbilityContext, name: string): Promise<void> {
  await OhmProbe.measure(context,name,async (): Promise<void> => {},async (): Promise<number> => {
    let count=0;
    for (let i=0;i<120;i++) {
      const response=await getWeatherUtil.getWeather(440300+i);
      count+=response.forecasts.length;
    }
    await new Promise<void>((resolve) => {setTimeout(resolve,1000);});
    return count;
  });
}
