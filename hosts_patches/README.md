# Host patch series

Each host directory holds the complete `git format-patch` series from the upstream base
commit to the dataset's `ohmbase` branch tip (build adaptation + all case commits).
Apply with `git am` to reconstruct the full dataset history including the unfixed/fixed
commits referenced by `cases/*/case.json`.

| Host | Upstream base | Upstream repo | Patches |
| --- | --- | --- | --- |
| browser | f44fff7 | https://github.com/langwudong/browser | 6 |
| wanharmony | dd45ad2 | https://github.com/zjmok/WanHarmony (dev) | 4 |
| jingmo | ddca186 | https://github.com/hefengbao/jingmo-for-HarmonyOS | 4 |
| cloudmusic | 724702c | https://github.com/Chenlvin/CloudMusic-HarmonyOSNext | 6 |
| ytmusic | f925981 | https://github.com/Charles-Stark/Youtube-Music-ArkTS-Clone | 4 |
| sheafreader | e04ef65 | https://github.com/simon2137/Sheaf-Reader | 5 |
| sepweather | e7b92b4 | https://github.com/SeaEpoch/SepWeather | 2 |
| weatherassistant | d3c7060 | https://github.com/AlatusLee/HarmonyOS-Next-Weather-Assistant | 3 |
| interviewapp | 1e05347 (origin/next) | https://github.com/HarmonyOS-Next/interview-handbook-project | 4 |

## Restore a host

```bash
git clone <upstream-repo> hosts/<name> && cd hosts/<name>
git checkout <upstream-base>
git checkout -b ohmbase
git am ../..//hosts_patches/<name>/*.patch   # from repo root: git -C hosts/<name> am ...
```

Case tags (`case/<id>/unfixed`, `case/<id>/fixed`) map to the commit hashes recorded in
`cases/<id>/case.json` — retag after `git am` if you want the same ergonomics:

```bash
git tag case/<id>/unfixed <unfixed_commit>
git tag case/<id>/fixed   <fixed_commit>
```

Note: ytmusic's upstream repository carries ~350 MB of rawfile audio at tip; the patch
series reconstructs the code without duplicating that history.
