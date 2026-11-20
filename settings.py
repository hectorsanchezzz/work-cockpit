"""What the settings page (out/settings.html) can read and change. Called by serve.py.

Where each setting lives:
  data/layout.json   main page sections: order and visibility
  data/sources.json  test sources, through sources.py
  config.json        lanes (order, name, hours_budget), stale_days, reminder_skip_lists, calendar_skip.
                     Edited in place: same key order and format, the previous file kept as config.json.bak.

Mapping rules and redact_words stay in config.json by hand, on purpose.
Every change is validated before anything is written; a bad request changes nothing.
"""
import json
import os
import shutil
import subprocess

import sources

ROOT = sources.ROOT
CONFIG = ROOT / "config.json"
LAYOUT = ROOT / "data" / "layout.json"
LOCAL = ROOT / "data" / "local.json"
from platform_util import EKCTL

# key: label on the settings page. The order here is the default page order.
SECTIONS = {
    "kpi": "Summary",
    "today": "Today and carried over",
    "think": "Needs thinking",
    "lanes": "Lanes",
    "prs": "Pull requests",
    "rize": "Tracked time",
    "claude": "Claude sessions",
    "days": "Day by day",
    "hours": "Hours",
    "dups": "Possible duplicates",
}


class Refused(Exception):
    pass


def _write(path, text):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def layout():
    """Ordered [{key, visible}]. Unknown keys are dropped; a section added later appears, visible, right after
    the section it follows in SECTIONS (or first)."""
    out, seen = [], set()
    try:
        saved = json.loads(LAYOUT.read_text())
    except (OSError, ValueError):
        saved = []
    for x in saved if isinstance(saved, list) else []:
        if isinstance(x, dict) and x.get("key") in SECTIONS and x["key"] not in seen and isinstance(x.get("visible"), bool):
            out.append({"key": x["key"], "visible": x["visible"]})
            seen.add(x["key"])
    keys = list(SECTIONS)
    for i, k in enumerate(keys):
        if k in seen:
            continue
        at = 0
        for prev in reversed(keys[:i]):
            pos = next((j for j, x in enumerate(out) if x["key"] == prev), None)
            if pos is not None:
                at = pos + 1
                break
        out.insert(at, {"key": k, "visible": True})
        seen.add(k)
    return out


def _config():
    return json.loads(CONFIG.read_text())


def _known_lists(cfg):
    """Reminder list names: every list in Reminders (ekctl), plus any already named in config or seen in data."""
    names = []  # Reminders' own spelling first, so the page shows the names as they appear there
    try:
        r = subprocess.run([EKCTL, "lists"], capture_output=True, text=True, timeout=15) if EKCTL else None
        names += [x["title"] for x in json.loads(r.stdout) if x.get("title")] if r else []
    except (OSError, ValueError, subprocess.SubprocessError, TypeError, KeyError):
        pass
    try:
        names += [r.get("list") for r in json.loads(LOCAL.read_text()).get("reminders", []) if r.get("list")]
    except (OSError, ValueError):
        pass
    names += list(cfg.get("reminder_skip_lists", [])) + list(cfg.get("reminder_lists", {}))
    out = {}
    for n in names:  # Reminders list names are matched without case
        out.setdefault(n.lower(), n)
    return sorted(out.values(), key=str.lower)


def _known_calendars(cfg):
    """Calendar names: those in config plus those seen in the last read. Skipped ones are never read, so config holds them."""
    names = set(cfg.get("calendar_skip", [])) | set(cfg.get("calendars", {})) | set(cfg.get("calendar_keyword_only", []))
    try:
        names |= {e.get("calendar") for e in json.loads(LOCAL.read_text()).get("events", []) if e.get("calendar")}
    except (OSError, ValueError):
        pass
    return sorted(names, key=str.lower)


def load():
    cfg = _config()
    on = sources.load()
    return {
        "sources": [{"key": k, "label": label, "on": on[k]} for k, (label, _) in sources.SOURCES.items()],
        "sections": [{**x, "label": SECTIONS[x["key"]]} for x in layout()],
        "lanes": [{"key": l["key"], "name": l.get("short") or l["name"], "hours_budget": l.get("hours_budget")} for l in cfg["lanes"]],
        "stale_days": int(cfg.get("stale_days", 14)),
        "reminder_skip_lists": cfg.get("reminder_skip_lists", []),
        "calendar_skip": cfg.get("calendar_skip", []),
        "known_lists": _known_lists(cfg),
        "known_calendars": _known_calendars(cfg),
    }


def _names(v, what):
    if not isinstance(v, list) or len(v) > 100:
        raise Refused(f"Too many {what}.")
    out = []
    for s in v:
        if not isinstance(s, str) or not s.strip() or len(s) > 100 or "\n" in s:
            raise Refused(f"One of the {what} is not a valid name.")
        if s.strip() not in out:
            out.append(s.strip())
    return out


def _merge_names(old, new, fold=False):
    """Keep the existing order for names that stay, append the new ones. Returns None when nothing changed."""
    key = (lambda s: s.lower()) if fold else (lambda s: s)
    if {key(s) for s in old} == {key(s) for s in new}:
        return None
    keep = {key(s) for s in new}
    out = [s for s in old if key(s) in keep]
    have = {key(s) for s in out}
    return out + [s for s in new if key(s) not in have]


def save(body):
    """Validate everything in body, then write what changed. Returns the set of things that changed:
    'sources', 'layout', 'config' and 'skips' (a skip list changed, so the sources must be read again)."""
    if not isinstance(body, dict):
        raise Refused("bad request")
    cfg = _config()
    changed = set()
    new_layout = new_sources = None

    if "sources" in body:
        s = body["sources"]
        if not isinstance(s, dict) or any(k not in sources.SOURCES or not isinstance(v, bool) for k, v in s.items()):
            raise Refused("bad sources")
        if any(sources.load()[k] != v for k, v in s.items()):
            new_sources = s

    if "sections" in body:
        s = body["sections"]
        if (not isinstance(s, list) or any(not isinstance(x, dict) or not isinstance(x.get("visible"), bool) for x in s)
                or sorted(x.get("key") or "" for x in s) != sorted(SECTIONS)):
            raise Refused("bad sections")
        s = [{"key": x["key"], "visible": x["visible"]} for x in s]
        if s != layout():
            new_layout = s

    if "lanes" in body:
        s = body["lanes"]
        old = {l["key"]: l for l in cfg["lanes"]}
        if not isinstance(s, list) or any(not isinstance(x, dict) for x in s) or sorted(x.get("key") or "" for x in s) != sorted(old):
            raise Refused("bad lanes")
        lanes = []
        for x in s:
            name, hours = x.get("name"), x.get("hours_budget")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60 or "\n" in name:
                raise Refused("Each lane needs a name of up to 60 characters.")
            if hours is not None and (isinstance(hours, bool) or not isinstance(hours, (int, float)) or not 0 <= hours <= 100):
                raise Refused("Hours per week must be between 0 and 100, or empty.")
            lane = dict(old[x["key"]])
            name = name.strip()
            if name != (lane.get("short") or lane["name"]):  # a renamed lane uses the new name everywhere
                lane["name"] = name
                lane.pop("short", None)
            if hours is not None and float(hours).is_integer():
                hours = int(hours)
            lane["hours_budget"] = hours
            lanes.append(lane)
        if lanes != cfg["lanes"]:
            cfg["lanes"] = lanes
            changed.add("config")

    if "stale_days" in body:
        v = body["stale_days"]
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 365:
            raise Refused("Days must be a whole number from 1 to 365.")
        if v != cfg.get("stale_days"):
            cfg["stale_days"] = v
            changed.add("config")

    for key, what, fold in (("reminder_skip_lists", "reminder lists", True), ("calendar_skip", "calendars", False)):
        if key in body:
            merged = _merge_names(cfg.get(key, []), _names(body[key], what), fold)
            if merged is not None:
                cfg[key] = merged
                changed |= {"config", "skips"}

    # Everything is valid: write.
    if "config" in changed:
        shutil.copy2(CONFIG, CONFIG.with_suffix(".json.bak"))
        _write(CONFIG, json.dumps(cfg, indent=1, ensure_ascii=False))
    if new_layout is not None:
        _write(LAYOUT, json.dumps(new_layout, indent=1))
        changed.add("layout")
    if new_sources is not None:
        sources.save(new_sources)
        changed.add("sources")
    return changed
