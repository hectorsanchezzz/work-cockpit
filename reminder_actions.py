"""Reminder actions from the cockpit page: one reminder, by id, through ekctl. Called by serve.py.

Actions:
  done     ekctl complete
  move     ekctl update --due (YYYY-MM-DD or 'YYYY-MM-DD HH:MM'). A reminder in Think goes back to the list
           it came from (named in its note), when that list still exists.
  nodate   ekctl update --clear-due
  rename   ekctl update --title
  cancel   append a note ("Cancelled in cockpit", or "... as a duplicate of: <kept title>"), stop a repeat,
           then complete. ekctl has no delete, on purpose, so a cancelled reminder stays in Completed.
  think    move it to the list called Think (any case) with no date, appending a note
           ("Moved to Think from <list> on <date>"). Refused if there is no Think list: ekctl cannot create one.

Every reminder is looked up among the open ones first, so the page can only touch a reminder that is
open and not in a skipped list. ekctl always gets an argument list, never a shell. Each write is
appended to logs/actions.log. Afterwards data/local.json is patched in place, so the page can be
re-rendered at once without a full refresh.
"""
import datetime as dt
import json
import os
import re
import subprocess

ROOT = __import__("pathlib").Path(__file__).resolve().parent
EKCTL = os.path.expanduser("~/bin/ekctl")
LOG = ROOT / "logs" / "actions.log"
LOCAL = ROOT / "data" / "local.json"
ACTIONS = {"done", "move", "nodate", "rename", "cancel", "think"}
FROM_RE = re.compile(r"Moved to Think from (.+?) on \d{4}-\d{2}-\d{2}")
ID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
DUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$")


class Refused(Exception):
    pass


def ek(*args):
    r = subprocess.run([EKCTL, *args], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200] or "ekctl failed")
    return r.stdout


def validate(req):
    if not isinstance(req, dict):
        raise Refused("bad request")
    action, rid = req.get("action"), req.get("id")
    if action not in ACTIONS or not isinstance(rid, str) or not ID_RE.match(rid):
        raise Refused("bad request")
    out = {"action": action, "id": rid}
    if action == "move":
        due = req.get("due")
        if not isinstance(due, str) or not DUE_RE.match(due):
            raise Refused("bad date")
        try:
            dt.datetime.strptime(due, "%Y-%m-%d %H:%M" if " " in due else "%Y-%m-%d")
        except ValueError:
            raise Refused("bad date")
        out["due"] = due
    if action == "rename":
        title = req.get("title")
        if not isinstance(title, str) or not title.strip() or len(title) > 300 or "\n" in title or "\r" in title:
            raise Refused("bad title")
        out["title"] = title.strip()
    if action == "cancel" and req.get("keep") is not None:
        keep = req.get("keep")
        if not isinstance(keep, str) or not ID_RE.match(keep) or keep == rid:
            raise Refused("bad request")
        out["keep"] = keep
    return out


def list_names():
    return [x["title"] for x in json.loads(ek("lists")) if x.get("title")]


def open_reminders(skip):
    rems = json.loads(ek("reminders"))
    return {r["id"]: r for r in rems if not r.get("completed") and (r.get("list") or "").lower() not in skip}


def log(line):
    LOG.parent.mkdir(exist_ok=True)
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG.open("a") as f:
        f.write(f"{stamp} {line}\n")


def run(req, skip):
    """Validate, check the reminder is open, act, log. Returns what changed, for patch()."""
    a = validate(req)
    rems = open_reminders(skip)
    r = rems.get(a["id"])
    if not r:
        raise Refused("That reminder is no longer open.")
    rid, action = a["id"], a["action"]
    title = r.get("title") or ""
    if action == "done":
        ek("complete", "--id", rid)
        detail = ""
    elif action == "move":
        args = ["update", "--id", rid, "--due", a["due"]]
        detail = f"due={a['due']} (was {r.get('due') or 'none'})"
        if (r.get("list") or "").lower() == "think":
            m = FROM_RE.search(r.get("notes") or "")
            back = m and next((n for n in list_names() if n.lower() == m.group(1).lower()), None)
            if back:
                args += ["--list", back]
                a["back"] = back
                detail += f" back to {json.dumps(back, ensure_ascii=False)}"
        ek(*args)
    elif action == "think":
        if (r.get("list") or "").lower() == "think":
            raise Refused("That reminder is already in Think.")
        name = next((n for n in list_names() if n.lower() == "think"), None)
        if not name:
            raise Refused("Add a list called Think in Reminders first.")
        old = (r.get("notes") or "").rstrip()
        note = f"Moved to Think from {r.get('list') or 'Reminders'} on {dt.date.today().isoformat()}"
        ek("update", "--id", rid, "--list", name, "--clear-due", "--notes", f"{old}\n\n{note}" if old else note)
        a["list"], a["from"] = name, r.get("list")
        detail = f"from {json.dumps(r.get('list') or '', ensure_ascii=False)} (was {r.get('due') or 'none'})"
    elif action == "nodate":
        ek("update", "--id", rid, "--clear-due")
        detail = f"(was {r.get('due') or 'none'})"
    elif action == "rename":
        ek("update", "--id", rid, "--title", a["title"])
        detail = f"title={json.dumps(a['title'], ensure_ascii=False)}"
    else:  # cancel
        if "keep" in a:
            kept = rems.get(a["keep"])
            if not kept:
                raise Refused("The reminder to keep is no longer open.")
            note = f"Cancelled in cockpit on {dt.date.today().isoformat()} as a duplicate of: {kept.get('title') or ''}"
            detail = f"duplicate of {a['keep']}"
        else:
            note = f"Cancelled in cockpit on {dt.date.today().isoformat()}"
            detail = ""
        old = (r.get("notes") or "").rstrip()
        args = ["update", "--id", rid, "--notes", f"{old}\n\n{note}" if old else note]
        if r.get("recurring"):
            args.append("--clear-recur")
        ek(*args)
        ek("complete", "--id", rid)
    log(f"{action} {rid} {json.dumps(title, ensure_ascii=False)} {detail}".rstrip())
    return a


def patch(a):
    """Apply the change to data/local.json so a re-render shows it. Call under the refresh lock."""
    data = json.loads(LOCAL.read_text())
    keep = []
    for r in data.get("reminders", []):
        if r.get("id") == a["id"]:
            if a["action"] in ("done", "cancel"):
                continue
            if a["action"] == "move":
                r["due"] = a["due"]
                if a.get("back"):
                    r["list"] = a["back"]
                    r.pop("from", None)
            elif a["action"] == "think":
                r["due"], r["list"], r["from"] = None, a["list"], a.get("from")
            elif a["action"] == "nodate":
                r["due"] = None
            elif a["action"] == "rename":
                r["title"] = a["title"]
        keep.append(r)
    data["reminders"] = keep
    data["edited"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    tmp = LOCAL.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(LOCAL)
