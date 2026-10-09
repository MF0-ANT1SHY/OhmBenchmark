# Raw measurement data

The raw device-measurement output is **not** stored in this repository. It lives on the
measurement workstation at:

```
/home/research/OhmBenchmark-data/
  measurements/   15 formal cases x {unfixed,fixed} x 3 runs
  experiments/    13 exploratory / excluded runs
```

The repository root contains `measurements` and `experiments` as **symlinks** into that
directory, so the existing scripts that resolve paths relative to the repo root keep
working unchanged (e.g. `measurements/summary.json`).

Per run directory:

- `trace.txt.gz` — original device hitrace text (app, scheduler, disk, Ark events)
- `perf.data` — original `hiperf record` sample file (these are large, up to ~125 MB)
- `perf-stat.txt` — process hardware/software performance counters
- `capture.txt`, `hilog.txt` — collection diagnostics and runtime application logs
- `result.json` — device monotonic elapsed time
- `*.jpeg` — UI screenshots before/after measurement

`data-inventory.txt` in `/home/research/OhmBenchmark-backup/` records every tracked data
file with its size as of the relocation.

## Restoring the layout elsewhere

```bash
git clone <repo> && cd <repo>
ln -s /path/to/OhmBenchmark-data/measurements measurements
ln -s /path/to/OhmBenchmark-data/experiments  experiments
```

The symlinks are intentionally untracked (gitignored), so a fresh clone simply starts
without them; create them only when you have the data directory available.
