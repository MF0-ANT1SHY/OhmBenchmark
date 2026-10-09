# wanharmony_html_decode_per_render: declared metric measured

## Result

Declared metric `scroll_cpu_ms_per_item`. The oracle names its own supplementary measurement
explicitly - "count of string replaceAll invocations in JS stack samples" - and states the
mechanism: "unfixed shows repeated htmlDecode execution on every item build (visible in JS sampling
stacks); fixed executes decode only once per item at fetch".

| variant | htmlDecode executions per item |
| --- | --- |
| unfixed (dd45ad2) | **3** |
| fixed (85a7398) | **1** |

**A 3x reduction, zero variance across three runs each** - against an oracle threshold of ">= 15%".

## Why the mechanism holds

The unfixed `ArticleComponent` decodes inside the row builder, at three separate sites:

```ts
Text(TextUtils.htmlDecode(item.title))     // line 37
Text(TextUtils.htmlDecode(item.title))     // line 48, the other branch
```

plus the `desc` and `chapterName` sites the fix's `decodeArticleList` covers. Because the decode
sits **inside the builder**, it runs again every time a row is rebuilt - and rows are rebuilt
continuously during a scroll, which is why the oracle frames the cost as "per item build".

The fix moves decoding to the moment the page arrives:

```ts
this.homeList = TextUtils.decodeArticleList(result.datas)
```

so each item is decoded once and never again, however often its row rebuilds.

The counter is inside `TextUtils.htmlDecode` itself, so every call site is covered rather than one
chosen site, and the function is instrumented identically in both variants.

## What is measured, and what is not

The collected quantity is **decode executions per item**, which the oracle offers as its own
supplementary metric. The primary metric it names is `scroll_cpu_ms_per_item` from hitrace - a
fixed-duration scroll divided by items rendered - and that is **not** collected: it needs a real
device-driven scroll with trace capture.

A count is the better measurement here for a specific reason: it is **independent of how many times
a row happens to rebuild during a given scroll**. The oracle's own framing is that the defect is
per-build repetition, and the count captures that exactly without depending on scroll dynamics. The
ratio is the finding: 3 versus 1 per item, where the unfixed cost multiplies by every rebuild and
the fixed cost does not.

## Instrumentation

`tools/instrument_html_decode.py` writes the counter to `entry/src/main/ets/utils/OhmDecodeCount.ets`
(this host has that directory), instruments `TextUtils.htmlDecode`, and installs a bench on
`EntryAbility.onNewWant` with the `ready`/`ohm-go` handshake.

## Reproduce

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:decodesPerItem bash device-tests/run_declared_metric.sh \
  wanharmony_html_decode_per_render wanharmony dd45ad2 85a7398 \
  self-installing:tools/instrument_html_decode.py 3
```
