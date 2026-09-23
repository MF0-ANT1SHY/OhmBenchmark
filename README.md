# OhmBenchmark: HarmonyOS/OpenHarmony Performance Bug Dataset

Migration of the Android performance-bug benchmark
(`/home/syang75/syang75/experiment/NonFunctionalAndroidCommits/telemetry/successful_case`, 60 cases, read-only)
to OpenHarmony / HarmonyOS NEXT host applications.

## Layout (planned)

- `toolchain/` — HarmonyOS command-line-tools + SDK (not committed, large binaries)
- `hosts/` — cloned host app repos (each with its own git history; unfixed/fixed commits created on top)
- `cases/<case_id>/` — per-case metadata: case.json (bundle, commits, description), trigger steps, test oracle, trace config
- `docs/` — survey and mapping notes

## Android case mechanism survey (source: 60 cases)

Dominant mechanism families:

1. Lazy vs eager loading (icons, drawables, previews) — dns66_eager_app_icons, listmyapps_eager_icons, alwayson_lazy_layout_previews
2. Caching / memoization (category IDs, statistics, metadata) — fdroid_category_id_cache, towercollector_statistics_cache, fdroid_precomputed_preferred_metadata
3. String assembly efficiency (StringBuilder, quadratic concat) — fdroid_method_e5d25ae8d0fa, lightning_bookmark_html_concatenation, fdroid_method_f3974898af92
4. Database: transactions, indexes, streaming, join elimination, temp DB — fdroid_repo_update_transaction, fdroid_suggested_version_index, fdroid_in_memory_temp_database, fdroid_remove_unused_apk_join, towercollector_integer_location_join, voipms_sql_message_filter, voipms_batch_conversation_delete, portauthority_oui_import_transactions
5. Parsing efficiency (DOM→SAX, regex-heavy parsing, SAX char buffer, parser rework) — avare_weather_dom_to_sax, dns66_hosts_file_parsing, fdroid_sax_character_allocation, calculator_matrix_parser
6. UI-thread offloading / callback throttling — portauthority_excessive_ui_callbacks, portauthority_ui_progress_predicate
7. View recycling / component reuse — listmyapps_view_recycling
8. Redundant paint/UI state — atmospherelogger_redundant_paint_state, atmospherelogger_batched_plot_lines, avare_draw
9. Network avoid-redundant-work (ETag, unchanged skip, size-before-hash) — gdroid_network cases, fdroid_method_2fc8060a5dc7, fdroid_skip_unchanged_*
10. Resource retention (sockets, caches) — dns66_expired_socket_retention, dns66_packet_cache_growth, portauthority_b311d3140b48
11. Deferred persistence / scheduling — calculator_deferred_*, portauthority_scan_scheduling, portauthority_socket_connect_timeout
12. I/O buffering — fdroid_buffered_stream_copy, fdroid_repo_count_streaming

## Host app candidates (all public, source-available)

| Repo | Category | Maps to Android mechanisms |
| --- | --- | --- |
| github.com/langwudong/browser | Browser (小狐狸浏览器, API18) | lightning bookmark/history/tab cases |
| github.com/awaLiny2333/LinysBrowser_NEXT | Browser | lightning cases |
| github.com/zjmok/WanHarmony | WanAndroid client | fdroid/gdroid catalog cases |
| github.com/Chenlvin/CloudMusic-HarmonyOSNext | Music (仿网易云) | list rendering, image load |
| github.com/linwu-hi/open_neteasy_cloud | Music (仿网易云) | list rendering, cache |
| github.com/hefengbao/jingmo-for-HarmonyOS | Reading/library DB app | towercollector/voipms RDB cases |
| github.com/WinWang/HarmoneyOpenEye | Feed/video (开眼) | alwayson/listmyapps list cases |
| github.com/OHPG/FinVideo | Jellyfin video client | network render, streaming copy |
| github.com/banggx/account_app_harmonyos | Accounting | calculator deferred save, stats cache |
| github.com/xiaoli8571/SSRVPN_Harmony | VPN/proxy | dns66 parsing/retention cases |
| github.com/Lancenas/joplin-hap | Notes (Joplin port) | DB batch cases |
| github.com/simon2137/Sheaf-Reader | RSS reader | SAX/parsing cases |
| github.com/SeaEpoch/SepWeather | Weather | avare weather parsing/paint |
| github.com/HarmonyOS-Next/interview-handbook-project | Content app 面试通 | font lookup, string building |

## Toolchain

- `commandline-tools-linux-x64-5.1.0.840.zip` from https://repo.huaweicloud.com/harmonyos/ohpm/5.1.0/ (no login needed)
- Node v24.19.0, OpenJDK 21 available locally
- Build gate: `hvigorw assembleHap` must PASS for both unfixed and fixed of every case
