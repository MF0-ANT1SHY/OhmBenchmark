# Oracle coverage

Of 30 cases: 8 satisfied, 1 counter-satisfied, 14 declared-collected-new, 2 mechanism-absent, 2 unsatisfied-overlap, 3 never-run.

| case | verdict | primitive | declared metric | collected metric |
| --- | --- | --- | --- | --- |
| `browser_eager_history_load` | satisfied | cpu | `trace_cpu_ms` | `trace_cpu_ms` |
| `browser_history_delete_no_transaction` | satisfied | elapsed | `elapsed_ms` | `elapsed_ms` |
| `browser_history_list_foreach` | counter-satisfied | count | `component_build_count_and_first_frame_ms` | `history_components_created` |
| `browser_insert_date_lookup_cache` | declared-collected-new | count | `rdb_statements_per_page_save` | `StatementCount` |
| `cloudmusic_indexof_in_render` | declared-collected-new | elapsed | `row_build_cpu_overhead` | `result` |
| `cloudmusic_local_song_memory_filter` | unsatisfied-overlap | elapsed | `elapsed_ms` | `elapsed_ms` |
| `cloudmusic_play_time_high_frequency_update` | declared-collected-new | count | `player_page_rerenders_per_minute` | `result` |
| `cloudmusic_search_result_foreach` | declared-collected-new | count | `search_list_render_cpu_and_jank` | `result` |
| `cloudmusic_songcard_artists_concat` | declared-collected-new | cpu | `row_appear_cpu_overhead` | `result` |
| `interviewapp_response_log_full_stringify` | never-run | cpu | `response_handler_cpu_ms` | — |
| `interviewapp_search_history_sync_flush` | declared-collected-new | count | `flush_count_per_search_burst` | `FlushCount` |
| `interviewapp_search_history_unbounded` | declared-collected-new | count | `history_entries_and_render_cost` | `result` |
| `jingmo_dataset_import_no_transaction` | satisfied | elapsed | `elapsed_ms` | `elapsed_ms` |
| `jingmo_random_poem_orderby_random` | satisfied | elapsed | `elapsed_ms` | `elapsed_ms` |
| `jingmo_sync_page_reimport` | satisfied | elapsed | `elapsed_ms` | `elapsed_ms` |
| `sepweather_font_register_per_page` | declared-collected-new | elapsed | `mainpage_build_ms` | `perCreation` |
| `sheafreader_article_list_foreach` | mechanism-absent | cpu | `article_row_build_count` | `article_components_created` |
| `sheafreader_extract_tag_tolowercase` | satisfied | cpu | `trace_cpu_ms` | `trace_cpu_ms` |
| `sheafreader_insert_duplicate_exception` | unsatisfied-overlap | cpu | `trace_cpu_ms` | `trace_cpu_ms` |
| `sheafreader_refresh_feeds_sequential` | satisfied | elapsed | `elapsed_ms` | `elapsed_ms` |
| `sheafreader_unread_counts_n_plus_1` | declared-collected-new | count | `sidebar_count_queries_per_refresh` | `QueryCount` |
| `wanharmony_history_log_materialization` | satisfied | cpu | `trace_cpu_ms` | `trace_cpu_ms` |
| `wanharmony_html_decode_per_render` | declared-collected-new | cpu | `scroll_cpu_ms_per_item` | `decodesPerItem` |
| `wanharmony_persisted_home_list_growth` | declared-collected-new | count | `persistent_write_bytes_per_loadmore` | `firstCycle` |
| `wanharmony_web_progress_log_storm` | declared-collected-new | count | `log_calls_per_pageload` | `progressValues` |
| `weatherassistant_http_session_leak` | mechanism-absent | external | `retained_fds_and_connections` | `fd_before+fd_after` |
| `weatherassistant_remote_weather_icons` | never-run | external | `icon_first_paint_ms_and_net_bytes` | — |
| `ytmusic_current_playing_timeupdate` | declared-collected-new | count | `player_page_updates_per_minute` | `JsonParseCount` |
| `ytmusic_history_json_parse_per_row` | declared-collected-new | count | `history_page_render_cpu_ms` | `JsonParseCount` |
| `ytmusic_search_no_debounce` | never-run | count | `search_requests_per_query` | — |
