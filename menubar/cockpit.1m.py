#!/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
# <swiftbar.title>Work Cockpit</swiftbar.title>
# <swiftbar.desc>What is left today, from ~/development/cockpit/out/summary.json</swiftbar.desc>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>false</swiftbar.hideSwiftBar>
"""SwiftBar plugin: reads the summary the refresh job writes. Reads only."""
import datetime as dt
import json
import os
from pathlib import Path

SUMMARY = Path.home() / "development/cockpit/out/summary.json"
APP = Path.home() / "Applications/Work Cockpit.app"
URL = "http://127.0.0.1:8765/"
UID = os.getuid()


def safe(s):
    s = str(s).replace("|", "/").replace("\n", " ").strip()
    return s.lstrip("-") or "?"


def age_min(iso):
    try:
        return (dt.datetime.now().astimezone() - dt.datetime.fromisoformat(iso)).total_seconds() / 60
    except (ValueError, TypeError):
        return None


try:
    s = json.loads(SUMMARY.read_text())
except Exception:
    print("Cockpit ? | sfimage=square.stack.3d.up")
    print("---")
    print("No summary yet. The refresh job writes it every 30 minutes.")
    print(f"Refresh now | bash=/bin/launchctl param1=kickstart param2=gui/{UID}/local.cockpit.refresh terminal=false refresh=true")
    raise SystemExit

old = age_min(s.get("generated"))
stale = old is None or old > 120
today = s.get("today") or []
now = dt.datetime.now().strftime("%H:%M")
# Left today: everything dated today except events whose start time has passed.
left = sum(1 for it in today if not (it.get("kind") == "ev" and ":" in (it.get("when") or "") and it["when"] < now))
# Compact on purpose: the notch hides menu bar items that do not fit.
title = f"{left} today" + (" old" if stale else "")
print(f"{title} | sfimage=square.stack.3d.up")
print("---")
print(f"{s['overdue']} overdue · {s['waiting']} waiting on you · {s['quiet']}/{s['lanes_total']} lanes quiet")
print("Menu bar shows what is left today; passed events drop off | size=11")
if s.get("errors"):
    print(f"{s['errors']} source error(s), see the page | color=#c4321f")
print("---")
print(f"Today ({left} left of {len(today)})")
for it in today[:15]:
    when = it.get("when") or ""
    gone = it.get("kind") == "ev" and ":" in when and when < now
    print(f"{safe(when):>7}  {safe(it['title'])[:70]} | font=Menlo size=12" + (" color=#8a8a8e" if gone else ""))
if len(today) > 15:
    print(f"{len(today) - 15} more on the page")
if not today:
    print("Nothing dated today")
print("---")
for ln in s.get("lanes", []):
    flag = " · quiet" if ln.get("quiet") else ""
    print(f"{safe(ln['name'])}: {ln['overdue']} overdue · {ln['waiting']} waiting{flag}")
print("---")
if APP.exists():
    print(f"Open Work Cockpit | bash=/usr/bin/open param1=-a param2=\"{APP}\" terminal=false")
else:
    print(f"Open Work Cockpit | href={URL}")
print(f"Refresh now | bash=/bin/launchctl param1=kickstart param2=gui/{UID}/local.cockpit.refresh terminal=false refresh=true")
gen = (s.get("generated") or "")[11:16]
lin = s.get("linear_generated") or ""
lin_txt = lin[11:16] if lin[:10] == (s.get("generated") or "")[:10] else lin[:10]
print(f"Updated {gen} · Linear {lin_txt} | size=11")
