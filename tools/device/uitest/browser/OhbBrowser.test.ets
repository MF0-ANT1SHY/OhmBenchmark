import { describe, it } from '@ohos/hypium';
import { Driver, Component, On } from '@ohos.UiTest';

/**
 * OHB reproducible UI flows for the browser host (小狐狸浏览器).
 * Run from host: aa test -b <bundle> -m entry_test -s unittest
 *   /ets/testrunner/OpenHarmonyTestRunner -s class ActsOhbBrowser#<it-name>
 *
 * Layout facts (1260x2844):
 *  - home search field: type Search (placeholder not exposed via hint)
 *  - home logo: Text 小狐狸浏览器
 *  - bottom toolbar buttons: back(126) forward(378) history(630)
 *    private(882) settings(1134), all at y=2615
 */

const TAG = 'OHB';

async function waitHome(driver: Driver): Promise<void> {
  await driver.waitForComponent(new On().text('小狐狸浏览器'), 10000);
}

async function submitSearch(driver: Driver, text: string) {
  await waitHome(driver);
  // The Search component's type does not surface in the driver tree; drive the
  // fixed field position instead (inputText performs its own click).
  await driver.inputText({ x: 636, y: 1441 }, text);
  await driver.delayMs(400);
  await driver.triggerKey(2054); // KEYCODE_ENTER -> onSubmit fires
  await driver.delayMs(2800); // page load + 保存浏览记录
}

export default function ohbBrowserTest() {
  describe('ActsOhbBrowser', () => {

    it('seed6', 0, async () => {
      const driver: Driver = Driver.create();
      for (let i = 0; i < 6; i++) {
        await submitSearch(driver, `ohm${Math.floor(Date.now() / 1000) % 100000}s${i}`);
        console.info(`${TAG} seed6 item ${i} done`);
      }
      console.info(`${TAG} seed6 ok`);
    })

    it('seed1', 0, async () => {
      const driver: Driver = Driver.create();
      await submitSearch(driver, `ohm${Math.floor(Date.now() / 1000) % 100000}x`);
      console.info(`${TAG} seed1 ok`);
    })

    it('openHistory', 0, async () => {
      const driver: Driver = Driver.create();
      await waitHome(driver);
      await driver.click(630, 2615);
      await driver.delayMs(1200);
      await driver.assertComponentExist(new On().text('浏览记录'));
      console.info(`${TAG} openHistory ok`);
    })

    it('scrollHistory', 0, async () => {
      const driver: Driver = Driver.create();
      await waitHome(driver);
      await driver.click(630, 2615);
      await driver.delayMs(1500);
      await driver.assertComponentExist(new On().text('浏览记录'));
      for (let i = 0; i < 6; i++) {
        await driver.swipe(630, 2200, 630, 800, 1200);
        await driver.delayMs(1200);
      }
      console.info(`${TAG} scrollHistory ok`);
    })

    it('clearHistory', 0, async () => {
      const driver: Driver = Driver.create();
      await waitHome(driver);
      await driver.click(1134, 2615); // settings gear (bottom-right)
      // findComponent misses dialog subwindows on this device; assert on text,
      // then drive the deterministic bottom-sheet positions instead.
      for (let i = 0; i < 8; i++) {
        await driver.delayMs(1000);
        try {
          await driver.assertComponentExist(new On().text('清除浏览记录'));
          break;
        } catch {
          // sheet not up yet
        }
      }
      await driver.click(276, 2275); // 清除浏览记录 row
      for (let i = 0; i < 8; i++) {
        await driver.delayMs(800);
        try {
          await driver.assertComponentExist(new On().text('确定要删除所有浏览记录？'));
          break;
        } catch {
          // confirm dialog not up yet
        }
      }
      await driver.click(897, 2628); // 确定 button
      await driver.delayMs(4000); // deletion runs in the capture window
      console.info(`${TAG} clearHistory ok`);
    })
  })
}
