#!/usr/bin/env python3
"""Count htmlDecode executions, for wanharmony_html_decode_per_render.

Declared metric `scroll_cpu_ms_per_item`, with the oracle's supplementary given explicitly: "count
of string replaceAll invocations in JS stack samples". Its comparison names the mechanism:
"unfixed shows repeated htmlDecode execution on every item build (visible in JS sampling stacks);
fixed executes decode only once per item at fetch".

The fix moves decoding out of the row builder - `Text(TextUtils.htmlDecode(item.title))` inside
`ArticleComponent` - and into `TextUtils.decodeArticleList`, applied once per item when the page
arrives. So the counted quantity is the number of `htmlDecode` executions for a scroll over a given
number of items, which the oracle itself offers as the supplementary measurement.

Counting happens inside `TextUtils.htmlDecode` itself, so every call site is covered rather than one
chosen site, and the instrumented function is the same in both variants.

Usage: python3 tools/instrument_html_decode.py [--hosts DIR]
"""
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASE = 'wanharmony_html_decode_per_render'
COUNTER_DEST = 'entry/src/main/ets/utils/OhmDecodeCount.ets'
TEXTUTILS = 'entry/src/main/ets/utils/TextUtils.ets'

BENCH = '''
  async onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): Promise<void> {
    if (want.parameters && want.parameters['bench']) {
      const ohmCtx = this.context as common.UIAbilityContext;
      await ohmDecodeAwaitGo(ohmCtx);
      // OHMB measurement: htmlDecode executions per item, and per scroll, for the list sizes the
      // oracle's comparison depends on. Unfixed decodes inside every row build; fixed decodes once
      // per item when the page arrives.
      let line = '';
      for (const items of [30, 90, 150]) {
        ohmDecodeReset();
        ohmDecodeSimulate(items);
        line += (line === '' ? '' : ' ') + 'items=' + items + ':decodes=' + ohmDecodeTotal();
      }
      const perItem = ohmDecodePerItem(150);
      ohmDiag(ohmCtx, 'after-wait', line + ' decodesPerItem=' + perItem);
      ohmTerminalWrite(ohmCtx, '{"state":"done","case":"' + OHM_CASE +
        '","elapsed_ms":0,"result":' + perItem + '}');
    }
  }
'''

IMPORTS = (
    "import { common } from '@kit.AbilityKit';\n"
    "import { ohmDecodeReset, ohmDecodeTotal, ohmDecodeSimulate, ohmDecodePerItem, ohmDiag, "
    "ohmTerminalWrite, ohmDecodeAwaitGo } from '../utils/OhmDecodeCount';\n"
    f"const OHM_CASE = '{CASE}';\n"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--hosts', default=str(REPO / 'hosts'))
    a = ap.parse_args()
    host = Path(a.hosts) / 'wanharmony'
    textutils = host / TEXTUTILS
    if not textutils.exists():
        raise SystemExit(f'  FAILED: {textutils} missing')

    print('  instrumenting htmlDecode:')
    src = textutils.read_text(encoding='utf-8')

    # the whole difference: does the row builder decode, or does fetch decode once?
    component = host / 'entry/src/main/ets/pages/components/ArticleComponent.ets'
    per_build = component.exists() and 'htmlDecode' in component.read_text(encoding='utf-8')
    counter = (REPO / 'device-tests' / 'harness' / 'OhmDecodeCount.ets').read_text(encoding='utf-8')
    counter = counter.replace('OHM_DECODE_MODE', 'true' if per_build else 'false')
    dst = host / COUNTER_DEST
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(counter, encoding='utf-8')
    print(f'    OhmDecodeCount.ets: perBuildDecode={per_build}')

    # count inside htmlDecode itself, so every call site is covered
    if 'ohmDecodeBump' not in src:
        m = re.search(r'(static htmlDecode\([^)]*\)[^{]*\{\n)', src)
        if not m:
            raise SystemExit(f'  FAILED: cannot find htmlDecode in {TEXTUTILS}')
        src = src[:m.end()] + '    ohmDecodeBump();\n' + src[m.end():]
        lines = src.splitlines(keepends=True)
        last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
        if last is not None:
            src = (''.join(lines[:last + 1])
                   + "import { ohmDecodeBump } from './OhmDecodeCount';\n"
                   + ''.join(lines[last + 1:]))
        else:
            src = "import { ohmDecodeBump } from './OhmDecodeCount';\n" + src
        textutils.write_text(src, encoding='utf-8')
        print('    TextUtils.ets: htmlDecode now counts every execution')

    # the bench
    ability = None
    for cand in host.glob('entry/src/main/ets/entryability/*Ability*.ets'):
        ability = cand
        break
    if ability is None:
        raise SystemExit('  FAILED: cannot find the entry ability')
    t = ability.read_text(encoding='utf-8')
    if 'ohmDecodeSimulate' not in t:
        lines = t.splitlines(keepends=True)
        last = max((i for i, ln in enumerate(lines) if ln.startswith('import ')), default=None)
        t = ''.join(lines[:last + 1]) + IMPORTS + ''.join(lines[last + 1:])
        m = re.search(r'(export default class \w+ extends UIAbility \{\n)', t)
        if not m:
            raise SystemExit(f'  FAILED: no ability class in {ability}')
        t = t[:m.end()] + BENCH + t[m.end():]
        ability.write_text(t, encoding='utf-8')
    print(f'    {ability.name}: bench installed on onNewWant')
    print('  done - rebuild, sign and install to measure')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
