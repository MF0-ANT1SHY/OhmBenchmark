# Oracle coverage

Of 30 cases: 3 counter-satisfied, 10 proxy, 4 collected-not-used, 13 never-run.

| case | verdict | primitive | declared metric | collected metric |
| --- | --- | --- | --- | --- |
| `browser_eager_history_load` | proxy | cpu | `startup_cpu_time_ms` | `trace_cpu_ms` |
| `browser_history_delete_no_transaction` | proxy | elapsed | `clear_history_wall_time_ms` | `elapsed_ms` |
| `browser_history_list_foreach` | counter-satisfied | count | `component_build_count_and_first_frame_ms` | `history_components_created` |
| `browser_insert_date_lookup_cache` | collected-not-used | count | `rdb_statements_per_page_save` | — |
| `cloudmusic_indexof_in_render` | never-run | elapsed | `row_build_cpu_overhead` | — |
| `cloudmusic_local_song_memory_filter` | proxy | elapsed | `search_result_latency_ms` | `elapsed_ms` |
| `cloudmusic_play_time_high_frequency_update` | never-run | count | `player_page_rerenders_per_minute` | — |
| `cloudmusic_search_result_foreach` | never-run | count | `search_list_render_cpu_and_jank` | — |
| `cloudmusic_songcard_artists_concat` | never-run | cpu | `row_appear_cpu_overhead` | — |
| `interviewapp_response_log_full_stringify` | never-run | cpu | `response_handler_cpu_ms` | — |
| `interviewapp_search_history_sync_flush` | collected-not-used | count | `flush_count_per_search_burst` | — |
| `interviewapp_search_history_unbounded` | collected-not-used | count | `history_entries_and_render_cost` | — |
| `jingmo_dataset_import_no_transaction` | proxy | elapsed | `dataset_import_wall_time_ms` | `elapsed_ms` |
| `jingmo_random_poem_orderby_random` | proxy | elapsed | `random_read_query_ms` | `elapsed_ms` |
| `jingmo_sync_page_reimport` | proxy | elapsed | `revisit_sync_page_cost` | `elapsed_ms` |
| `sepweather_font_register_per_page` | never-run | elapsed | `mainpage_build_ms` | — |
| `sheafreader_article_list_foreach` | counter-satisfied | count | `article_row_build_count` | `article_components_created` |
| `sheafreader_extract_tag_tolowercase` | proxy | cpu | `feed_parse_cpu_ms` | `trace_cpu_ms` |
| `sheafreader_insert_duplicate_exception` | proxy | cpu | `no_op_refresh_cpu_ms` | `trace_cpu_ms` |
| `sheafreader_refresh_feeds_sequential` | proxy | elapsed | `refresh_all_wall_time_ms` | `elapsed_ms` |
| `sheafreader_unread_counts_n_plus_1` | collected-not-used | count | `sidebar_count_queries_per_refresh` | — |
| `wanharmony_history_log_materialization` | proxy | cpu | `title_event_cpu_ms` | `trace_cpu_ms` |
| `wanharmony_html_decode_per_render` | never-run | cpu | `scroll_cpu_ms_per_item` | — |
| `wanharmony_persisted_home_list_growth` | never-run | count | `persistent_write_bytes_per_loadmore` | — |
| `wanharmony_web_progress_log_storm` | never-run | count | `log_calls_per_pageload` | — |
| `weatherassistant_http_session_leak` | counter-satisfied | external | `retained_fds_and_connections` | `fd_before+fd_after` |
| `weatherassistant_remote_weather_icons` | never-run | external | `icon_first_paint_ms_and_net_bytes` | — |
| `ytmusic_current_playing_timeupdate` | never-run | count | `player_page_updates_per_minute` | — |
| `ytmusic_history_json_parse_per_row` | never-run | count | `history_page_render_cpu_ms` | — |
| `ytmusic_search_no_debounce` | never-run | count | `search_requests_per_query` | — |
