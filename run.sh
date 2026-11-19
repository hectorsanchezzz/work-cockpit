#!/bin/bash
# Refresh the cockpit: collect local sources, fetch Linear, the enabled test sources (extras.py), render (v2 data and summary, then the live D page), build the local page.
# Run by launchd (local.cockpit.refresh) every 30 minutes. Read-only towards every source.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/bin"
cd "$(dirname "$0")"
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
LOCK=/tmp/cockpit-refresh.lock
mkdir "$LOCK" 2>/dev/null || { echo "$(date '+%F %T') already running, skipped"; exit 0; }
trap 'rmdir "$LOCK"' EXIT
echo "== $(date '+%F %T') refresh"
"$PY" collect.py || echo "collect.py failed"
"$PY" linear_fetch.py
"$PY" extras.py || echo "extras.py failed"
"$PY" render_v2.py || exit 1
"$PY" proposals.py --live || echo "proposals.py --live failed, serving v2"
"$PY" build_local.py
