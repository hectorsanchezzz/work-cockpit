#!/usr/bin/env python3
"""Shared data model for the work cockpit pages (v1 render.py, v2 render_v2.py).

Output: out/cockpit.html (an Artifact page body). Titles and IDs only, no notes,
no client details. No em dashes in anything rendered.
"""
import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text())
LOCAL = json.loads((ROOT / "data" / "local.json").read_text())
LIN = json.loads((ROOT / "data" / "linear.json").read_text())
TODAY = dt.date.today()
STALE = int(CFG.get("stale_days", 14))
LANES = [l["key"] for l in CFG["lanes"]]
PRIO = {1: "Urgent", 2: "High", 3: "Medium", 4: "Low", 0: ""}
EMOJI = re.compile("[\U00010000-\U0010FFFF☀-➿️‍]")


def clean(s):
    s = str(s or "")
    s = s.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ").replace("–", "-")
    s = EMOJI.sub("", s)
    for w in CFG.get("redact_words", []):
        s = re.sub(re.escape(w), "[client]", s, flags=re.I)
    return html.escape(re.sub(r"\s+", " ", s).strip())


def d(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def age(s):
    x = d(s)
    return None if x is None else (TODAY - x).days


def fmt_age(n):
    if n is None:
        return "never"
    return "today" if n <= 0 else f"{n}d ago"


def kw_lane(title):
    t = (title or "").lower()
    for k, lane in CFG.get("title_keywords", {}).items():
        if k.lower() in t:
            return lane
    return None


def linear_lane(iid, project):
    if project and project in CFG["linear_projects"]:
        return CFG["linear_projects"][project]
    return CFG["linear_team_default"].get(iid.split("-")[0], "personal")


def reminder_lane(r):
    return kw_lane(r["title"]) or CFG["reminder_lists"].get((r.get("from") or r.get("list") or "").lower(), "personal")


def event_lane(e):
    lane = kw_lane(e["title"])
    if lane:
        return lane
    if e["calendar"] in CFG.get("calendar_keyword_only", []):
        return "personal"
    return CFG["calendars"].get(e["calendar"], "personal")


def repo_lane(full):
    owner, name = full.split("/", 1)
    for k, lane in CFG.get("github_repo_keywords", {}).items():
        if k in name.lower():
            return lane
    return CFG["github_owners"].get(owner)


def local_repo_lane(r):
    p = r["path"].lower()
    for k, lane in CFG.get("code_path_keywords", {}).items():
        if k.lower() in p:
            return lane
    return repo_lane(r["repo"]) if r.get("repo") else None


def lin_url(iid):
    return f"https://linear.app/axisdatalabs/issue/{iid}"


# ---------- assemble per-lane data ----------
lanes = {k: {"waiting": [], "overdue": [], "started": [], "todo": [], "reminders": [], "events": [],
             "touch": {}} for k in LANES}


def bump(lane, source, date):
    if lane not in lanes or not date:
        return
    t = lanes[lane]["touch"]
    if source not in t or date > t[source]:
        t[source] = date


for iid, title, project, updated, due in LIN.get("aleix_review", []):
    lane = linear_lane(iid, project)
    lanes[lane]["waiting"].append({"kind": "Review", "id": iid, "title": title, "date": updated,
                                   "url": lin_url(iid), "note": "Aleix, In Review"})

for bucket in ("mine_started", "mine_todo"):
    for iid, title, status, project, due, updated, prio in LIN.get(bucket, []):
        lane = linear_lane(iid, project)
        item = {"id": iid, "title": title, "status": status, "due": due, "updated": updated,
                "prio": prio or 0, "url": lin_url(iid)}
        lanes[lane]["started" if bucket == "mine_started" else "todo"].append(item)
        bump(lane, "Linear", updated)
        if due and d(due) and d(due) < TODAY:
            lanes[lane]["overdue"].append({"kind": "Linear", "id": iid, "title": title, "due": due,
                                           "url": lin_url(iid)})

for p in LOCAL.get("prs", []):
    lane = repo_lane(p["repo"])
    if not lane:
        continue
    short = p["repo"].split("/", 1)[1]
    kind = "Review requested" if p["kind"] == "review" else ("Draft PR" if p["draft"] else "Open PR")
    lanes[lane]["waiting"].append({"kind": kind, "id": f"{short}#{p['number']}", "title": p["title"],
                                   "date": p["updated"], "url": p["url"]})
    bump(lane, "Code", p["updated"])

for repo, date in LOCAL.get("commits", {}).items():
    lane = repo_lane(repo)
    if lane:
        bump(lane, "Code", date)

for r in LOCAL.get("local_repos", []):
    lane = local_repo_lane(r)
    if lane:
        for d_ in (r.get("commit"), r.get("edit")):
            if d_:
                bump(lane, "Code", d_)

for lane, v in LOCAL.get("vault", {}).items():
    bump(lane, "Vault", v["date"])

for r in LOCAL.get("reminders", []):
    lane = reminder_lane(r)
    if lane not in lanes:
        continue
    lanes[lane]["reminders"].append(r)
    if r.get("due") and d(r["due"]) and d(r["due"]) < TODAY:
        lanes[lane]["overdue"].append({"kind": "Reminder", "id": r.get("list") or "", "title": r["title"],
                                       "due": r["due"][:10], "url": None})

for e in LOCAL.get("events", []):
    lane = event_lane(e)
    if lane in lanes:
        lanes[lane]["events"].append(e)


def next_actions(L):
    out = []
    started = [i for i in L["started"] if i["status"] == "In Progress"]
    started.sort(key=lambda i: ((i["prio"] or 9), -(d(i["updated"]) or TODAY).toordinal()))
    for i in started[:3]:
        out.append({"src": "In Progress", "id": i["id"], "title": i["title"], "url": i["url"],
                    "meta": PRIO.get(i["prio"], "")})
    if len(out) < 3:
        rems = [r for r in L["reminders"] if r.get("due") and d(r["due"]) and d(r["due"]) >= TODAY]
        rems.sort(key=lambda r: r["due"])
        for r in rems[: 3 - len(out)]:
            out.append({"src": "Reminder", "id": "", "title": r["title"], "url": None, "meta": f"due {r['due'][:10]}"})
    if len(out) < 3:
        todo = sorted(L["todo"], key=lambda i: ((i["prio"] or 9), -(d(i["updated"]) or TODAY).toordinal()))
        for i in todo[: 3 - len(out)]:
            out.append({"src": "Todo", "id": i["id"], "title": i["title"], "url": i["url"],
                        "meta": PRIO.get(i["prio"], "")})
    if len(out) < 3:
        rems = [r for r in L["reminders"] if not r.get("due") and (r.get("list") or "").lower() != "think"]
        for r in rems[: 3 - len(out)]:
            out.append({"src": "Reminder", "id": "", "title": r["title"], "url": None, "meta": "undated"})
    return out


