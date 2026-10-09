# Two cases whose declared metric is collected but whose ranges interleave

Making `classify()` apply the same rule as the contract - declared metric collected **and** ranges
disjoint - surfaced two cases that a name match had been calling satisfied.

| case | unfixed | fixed | reading |
| --- | --- | --- | --- |
| `cloudmusic_local_song_memory_filter` | 24.3 / 73.0 / 109.7 | 65.5 / 82.0 / 175.8 | **fixed is slower**, ranges interleave |
| `sheafreader_insert_duplicate_exception` | 23463.5 / 27458.4 / 37015.4 | 24176.7 / 25597.2 / 26290.9 | interleaved, 13.5% |

## The original session had already reached the same conclusion

Both cases carry `status: 未复现稳定改善` in `measurements/results.json`, with notes saying so
directly:

- `cloudmusic_local_song_memory_filter`: *"1000 首元数据，原页面检索方法调用 10 次；未出现稳定改善"* -
  1000 songs of metadata, the original page's search method called 10 times; no stable improvement.
- `sheafreader_insert_duplicate_exception`: *"重复插入：两版范围重叠，差异不稳定"* - duplicate insert:
  the two versions' ranges overlap, the difference is unstable.

So the corrected rule now **agrees with the original session** on both. Before the fix the
name-match rule had silently promoted them to `satisfied`, overstating progress on exactly the cases
the benchmark had recorded as not reproducing.

`cloudmusic_local_song_memory_filter` is the more striking: the fixed build is *slower* on all three
runs. An earlier revision of its oracle re-declared `search_result_latency_ms` to `elapsed_ms` on the
grounds that they were the same quantity. The quantity is the same, but the case does not separate on
it, and the revision now records that rather than implying otherwise.

## Effect on the counts

| verdict | before the fix | after |
| --- | --- | --- |
| `satisfied` | 10 | 8 |
| `unsatisfied-overlap` | - | 2 |

Summary and contract now agree at **8**, and `unsatisfied-overlap` is a distinct verdict rather than
a case being quietly counted as a success.

## What remains

- `sheafreader_insert_duplicate_exception` - declared metric collected, ranges interleave. Needs a
  larger fixture or a better-separated measurement before it can be called a clear difference.
- `cloudmusic_local_song_memory_filter` - same, and with the fixed build measuring slower, which is a
  finding about the case and not only about the measurement.
