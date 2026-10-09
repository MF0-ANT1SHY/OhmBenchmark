# sepweather_font_register_per_page: declared metric measured

## Result

Declared metric `mainpage_build_ms`, whose oracle states the mechanism: "unfixed shows TTF file
reads + font registration work in the page-build path on every creation; fixed only on the first".
The countable cost driver is registerFont work per page creation.

| variant | registrations per MainPage creation |
| --- | --- |
| unfixed (49e6faf) | **2.0** |
| fixed (cba3514) | **0.1** |

**A 20x reduction.** The unfixed page registers both fonts (`sepifont`, `DINCOROS`) in
`aboutToAppear` on every creation, so each recreation re-reads and re-parses the TTFs. The fixed
page guards on a process-level flag, so the work happens once across 20 creations - `2/20 = 0.1` -
and every later creation does none.

The per-creation figure is an average over 20 creations, which is why the fixed value is
fractional: that is the point of the fix, amortising once-per-process work over page lifecycles.

## This host had no harness at all

sepweather had no measurement patch, no probe and no bench, so one was built from scratch following
the pattern proven on ytmusic, wanharmony and cloudmusic:

- `entry/src/main/ets/utils/OhmFontCount.ets` - counter, the variant's registration behaviour, the
  diag and terminal writers, and the `ready`/`ohm-go` handshake. This host has no `ets/utils/`
  directory, so it is created;
- `EntryAbility.onNewWant` - runs the measurement on a `bench` want parameter;
- `MainPage.ets` - **both** real `font.registerFont(` sites are counted, so a genuine page creation
  would also be measured.

The instrumenter detects the variant from the source: the presence of `MainPage.fontsRegistered` is
the entire difference.

## What is measured, and what is not

The collected quantity is registrations per creation, which is the work the oracle describes as
happening "in the page-build path on every creation". The primary metric is wall-clock
`mainpage_build_ms` from the page's first build event to first frame, which is **not** collected: it
needs ace trace capture across real page recreations.

A count is the sounder measurement here because the defect is *repeated work per creation*, and the
count states that directly rather than depending on how long a TTF read happened to take on a given
run. What it does not establish is the millisecond cost of that work on this device.

## Reproduce

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:perCreation bash device-tests/run_declared_metric.sh \
  sepweather_font_register_per_page sepweather 49e6faf cba3514 \
  self-installing:tools/instrument_font_register.py 3
```

Note the commits are the **reconstructed** ones: the recorded `30cc357`/`e720e21` do not resolve in
this repository because `git am` rewrote them (`hosts_patches/REPRODUCE.md`).
