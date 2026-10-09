# OhmBenchmark — HarmonyOS/OpenHarmony Performance Bug Dataset

30 reproducible performance-bug cases on OpenHarmony / HarmonyOS NEXT, migrated from an
Android performance-bug benchmark (`NonFunctionalAndroidCommits`, 60 cases, read-only source).

Each case is a pair of builds — **unfixed** (contains the performance bug) and **fixed**
(repaired, behavior close to upstream) — of a **real open-source HarmonyOS application**,
plus the metadata needed to run the case on a device later: trigger steps, hitrace capture
config, and a test oracle.

## Dataset at a glance

- **30 cases** across **9 host applications** (all public GitHub projects)
- Categories: 16 latency, 11 cpu, 3 resource_retention
- Every unfixed and fixed commit builds successfully (`hvigorw assembleHap`, see `build_results.jsonl`)
- Full index: [`manifest.json`](manifest.json) · per-case metadata: [`cases/<id>/case.json`](cases)

## Layout

```
hosts/            cloned host repos (gitignored here; each has ohmbase branch + case/* tags)
  <host>/           e.g. hosts/browser — base + adapt + unfixed/fixed commits, tags case/<id>/{unfixed,fixed}
cases/<id>/
  case.json       bundle name, commits, bug description, android source case, trigger steps,
                  test oracle (metric + comparison), hitrace capture config
  fix.patch       the unfixed→fixed diff
hosts_patches/    per-host git format-patch series (upstream base → all dataset commits),
                  see hosts_patches/README.md for full reconstruction instructions
measurements/     raw device measurements (NOT in this repo; see DATA.md)
experiments/      exploratory runs (NOT in this repo; see DATA.md)
manifest.json     machine-readable index of all 30 cases
tools/
  strip_signing.py  removes local signing configs for headless builds
  verify_all.sh     rebuilds every unfixed/fixed commit and records PASS/FAIL
build_results.jsonl  output of the final verification sweep
```

## Host applications

| Host | App | Bundle | Cases |
| --- | --- | --- | --- |
| hosts/browser | 小狐狸浏览器 (browser) | com.example.nanvision | 4 |
| hosts/wanharmony | WanAndroid client | org.example.wan.ohos | 4 |
| hosts/jingmo | 京墨文库 (reading library, RDB) | com.hefengbao.jingmo.hw | 3 |
| hosts/cloudmusic | 仿网易云音乐 (music player) | cc.chenlvin.cloudmusic | 5 |
| hosts/ytmusic | YouTube Music clone | com.example.myapplication | 3 |
| hosts/sheafreader | 束阅 RSS reader | com.sheafreader.hm | 5 |
| hosts/sepweather | SepWeather 天气 | cn.seayj.sepweather | 1 |
| hosts/weatherassistant | Weather Assistant | com.alatus.futureweather | 2 |
| hosts/interviewapp | 面试通 (interview content app) | com.itcast.pass_interview | 3 |

## Case families (mapped from the Android benchmark)

- **Lazy rendering / view recycling**: ForEach→LazyForEach (browser history list, cloudmusic
  search results, sheafreader article list/grid)
- **Eager start-up work**: full-history DB load at startup (browser), re-registration of
  custom fonts per page (sepweather), per-visit dataset re-import (jingmo)
- **Redundant per-row work**: htmlDecode per render (wanharmony), JSON.parse ×4 per row
  (ytmusic), indexOf per row build (cloudmusic), toLowerCase copy per parsed tag (sheafreader)
- **Database**: transactions for bulk delete/import (browser, jingmo), batchInsert, SQL-side
  filtering (cloudmusic), N+1 count queries → GROUP BY (sheafreader), ORDER BY random() →
  indexed range scan (jingmo), duplicate handling via conflict resolution instead of
  exceptions (sheafreader)
- **State-update / callback storms**: millisecond-precision playback state (cloudmusic,
  ytmusic), per-keystroke network search (ytmusic), per-event progress logging (wanharmony)
- **String/serialization**: loop concatenation → join (cloudmusic), full-payload stringify
  for logs (wanharmony, interviewapp)
- **Network/resource**: static assets fetched from CDN → local resources (weatherassistant),
  HTTP sessions never destroyed (weatherassistant), sequential feed fetching → bounded
  concurrency (sheafreader)
- **Retention/unbounded growth**: persisted infinite-scroll list (wanharmony), search history
  without bound (interviewapp)

No case uses sleeps, dummy loops, artificial delays, or workloads unrelated to app behavior.
All injected bugs are small, realistic refactors of real code paths; each `fix.patch` shows
the unfixed→fixed diff (typically 10–80 lines).

## Toolchain

- `toolchain/command-line-tools` 5.1.0.840 (HarmonyOS SDK API 18, hvigor 5.18.5, ohpm 5.1.3)
  from https://repo.huaweicloud.com/harmonyos/ohpm/5.1.0/ (no login required)
- Build: `hvigorw --mode module -p product=default -p buildMode=debug assembleHap --no-daemon`
  (unsigned debug HAPs; sign with DevEco auto-signature before device deployment)

### Rebuild a case

```bash
export PATH=$PWD/toolchain/command-line-tools/bin:$PATH
export DEVECO_SDK_HOME=$PWD/toolchain/command-line-tools/sdk
git -C hosts/browser checkout case/browser_eager_history_load/unfixed
(cd hosts/browser && ohpm install --all && hvigorw --mode module -p product=default \
  -p buildMode=debug assembleHap --no-daemon)
```

### Re-verify everything

```bash
bash tools/verify_all.sh          # writes build_results.jsonl; exit 0 = all PASS
```

## Device workflow (once hardware is available)

1. Checkout the case's `unfixed` tag, build, install (sign first), run `trigger_steps`
   from `cases/<id>/case.json` while capturing the configured hitrace.
2. Repeat per the case's repetition count; then checkout `fixed`, rebuild, reinstall,
   repeat identically.
3. Evaluate `test_oracle.metric` on both trace sets and check the stated `comparison`
   (e.g. fixed ≥ 20% lower startup CPU, zero icon CDN bytes, 1 flush instead of 10).

## Upstream bases

Each host's `ohmbase` branch = upstream commit + a build-only adaptation commit
(signing strip / SDK-field downgrade / lockfile refresh). `case.json` records
`upstream_base_commit` where the base differs from upstream HEAD. See the Android
source benchmark for the original 60 cases and their evidence format.
