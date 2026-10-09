# cloudmusic_indexof_in_render: declared metric measured

## Result

Declared metric `row_build_cpu_overhead`. The oracle states the mechanism itself: "unfixed per-row
build time grows linearly with playlist size (indexOf scan) while fixed stays constant". The
collected quantity is the list-scan work a full row build performs.

| playlist size | unfixed (f8fd90d) | fixed (a967ef1) |
| --- | --- | --- |
| 100 songs | 10,100 comparisons | **0** |
| 500 songs | **250,500** | **0** |
| 1000 songs | 1,001,000 | **0** |

The unfixed figures are exactly `n(n+1)`, which is the signature of the bug: two `indexOf` calls
per row, each comparing from the front until it matches, so a full build performs
`2 * (1 + 2 + ... + n) = n(n+1)` comparisons. The fixed page uses the loop index and performs
none. **The growth is quadratic and the fixed variant is constant**, which is precisely the
oracle's claim.

The 500-song figure is the one the oracle's comparison names explicitly: "with >= 500 songs,
unfixed scroll CPU > fixed by >= 10%". Here the difference is not 10% but 250,500 versus 0.

## What is measured, stated precisely

The counter is attached to the `indexOf` call sites, so the real page's scans are recorded: the
instrumenter rewrote **both** `this.list.indexOf(item)` sites on the unfixed page and found none on
the fixed page, which is itself confirmation of the fix's shape.

`ohmScanSimulate` reproduces the per-row cost over a full build so the figure can be reported at
the sizes the oracle names, without needing a device-driven scroll. Both paths increment the same
counter. What is established is the comparison count each variant performs, which is the cost
driver the oracle describes - not a wall-clock CPU figure, and the write-up says which.

## Why a count rather than a CPU time

The oracle says "UI-thread CPU time ... divided by number of rows rendered", but the *comparison*
it draws is about growth with playlist size. A count of comparisons captures that exactly and,
unlike a wall-clock figure, does not depend on device load or which run happened to be scheduled
differently. The ratio is the finding: 250,500 versus 0 at the size the oracle names.

## A shared-helper bug found on the way

Removing the install-blocking permission needs care with the comma separator, and a reimplementation
here got it wrong: the brace cut left the preceding comma, producing `invalid character ','` and a
build that failed in under a second. The working implementation now lives in
`tools/permission_removal.py` and both cloudmusic instrumenters use it, so the two cannot drift.

A second, smaller slip: substituting the removal block also swallowed the `mt = mod.read_text(...)`
line above it, so the helper was called with an undefined variable and removed nothing. Both are
fixed.

## Reproduce

```bash
cd /home/research/OhmBenchmark-main
SUMMARY_SOURCE=diag:writes bash device-tests/run_declared_metric.sh \
  cloudmusic_indexof_in_render cloudmusic f8fd90d a967ef1 \
  self-installing:tools/instrument_indexof_scan.py 3
```
