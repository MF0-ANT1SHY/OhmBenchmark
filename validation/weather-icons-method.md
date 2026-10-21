# Weather icon cold-launch acceptance

This revised case uses business-only release HAPs. The application contains no measurement hooks, counters, readiness endpoints, or acceptance thresholds. Only the ordinary forecast origin (both variants) and image origin (unfixed) change. Fixed keeps the original bundled icons.

## Declared conditions

- Device is attached to the HKRC Windows laptop through Tailscale; use `Remote('hkrc')` for HDC. Signing remains separate.
- `tools/weather_workstation_lease.py` serves ordinary four-day forecasts and the four images extracted byte-for-byte from the fixed signed HAP. It runs for at most 7,200 seconds on workstation port 18492. Install its `weather_data_service.py` and `workstation_process.py` dependencies and `ordinary-icons` directory beside it.
- Establish HDC reverse forwarding for port 18492 inside the capture connection. The image service explicitly delays each image response by four seconds. Forecast responses are not deliberately delayed.
- Each trial force-stops the app and clears its cache with native `bm clean -n com.alatus.futureweather -c`. It does not clear business data. This is a cold-cache claim, not a warm-cache claim. The original invalid provider key is not repaired or claimed to work.
- `tools/capture_weather_icons.py` collects three paired launches and original native PNG frames. The HKRC image-analysis environment uses Pillow. The baseline must not show the completed forecast; the last frame must match all nine reference image regions exactly. Forecast text and requests must also match.

## Acceptance and provenance

`tools/accept_weather_icon_evidence.py` independently re-reads original frames, request receipts, native process identity, signed HAP identities, and scheduler traces. Each unfixed lower timing bound must be at least twice the paired fixed upper timing bound; the median must also reach 2.0. Scheduler CPU is diagnostic only, not a CPU-improvement claim.

The three conservative ratios are approximately 2.304, 2.222, and 2.320. Original contracts and workloads remain archived. The exploratory screen is not counted as formal acceptance.

Round 2 unfixed completed on HKRC but its SSH return timed out. Original remote files were recovered without rerunning the workload. Its before-service anchor is the preceding fixed round's completed service verification; the same PID, process creation identity, source, and content hashes were verified after recovery. The original native receipt is retained separately and checked unchanged. See `weather-icons-transport-recovery.json`. Later trials persist the before-service verification immediately.

Only the audited HAP, app-only native profile, ordinary UI workload, reproduction script, and symptom are exported to the diagnosis workspace. Reference pixels, image readiness classifications, oracle thresholds, paired measurements, and evaluator service receipts stay outside the app and agent export.
