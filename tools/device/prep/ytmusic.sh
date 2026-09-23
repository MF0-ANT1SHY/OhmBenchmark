#!/bin/bash
# ytmusic backend (host-level prep, applies to every case of this host) yt.c12k.dev is dead (NXDOMAIN). Point the app at the
# local mock (device localhost:8978 via `hdc rport`) in BOTH variants so the
# per-keystroke-request vs debounced mechanism stays measurable.
grep -rl "yt.c12k.dev" entry/src/main/ets/ | xargs sed -i '' 's#https://yt.c12k.dev#http://127.0.0.1:8978#g'
echo "patched: $(grep -rl '127.0.0.1:8978' entry/src/main/ets/ | tr '\n' ' ')"
