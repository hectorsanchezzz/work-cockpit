#!/usr/bin/env python3
"""Read-only collector for the work cockpit.

Pulls Calendar from iCal feeds (config calendar_ics) and, on macOS, Apple Reminders and Calendar
(via ~/bin/ekctl, read commands only),
GitHub PRs and recent commits (via gh, one call per account), and the last
vault commit per lane folder, plus the last commit and newest
uncommitted edit in every git repo under code_root (read-only git log/status). Writes data/local.json. Never writes to any source.
"""
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text())
from platform_util import EKCTL  # None when there is no ekctl (Windows)
errors = []


def run(cmd, env=None, timeout=60):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1:] or ["failed"])
    return r.stdout


def gh_env(user):
    import shutil
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI (gh) is not installed")
    tok = subprocess.run(["gh", "auth", "token", "-u", user], capture_output=True, text=True).stdout.strip()
    if not tok:
        raise RuntimeError(f"no gh token for {user}")
    env = dict(os.environ)
    env["GH_TOKEN"] = tok
    return env


def reminders():
    if not EKCTL:  # Apple Reminders only exists on macOS; off elsewhere
        return []
    skip ={s.lower() for s in CFG["reminder_skip_lists"]}
    out = []
    for r in json.loads(run([EKCTL, "reminders"])):
        if r.get("completed") or (r.get("list") or "").lower() in skip:
            continue
        x = {k: r.get(k) for k in ("id", "title", "list", "section", "due", "priority", "recurring")}
        if (r.get("list") or "").lower() == "think":  # keep only where it came from, never the notes
            m = re.search(r"Moved to Think from (.+?) on \d{4}-\d{2}-\d{2}", r.get("notes") or "")
            if m:
                x["from"] = m.group(1)
        out.append(x)
    return out


def events_via_launchd():
    """Background runs: macOS only lets ekctl read Calendar when ekctl itself is the
    launched program, so the local.cockpit.calendar job runs `ekctl agenda --days 8`
    and writes its output to data/agenda.json, which is read and then removed."""
    import time
    out = ROOT / "data" / "agenda.json"
    out.write_text("")
    subprocess.run(["/bin/launchctl", "kickstart", f"gui/{os.getuid()}/local.cockpit.calendar"],
                   capture_output=True, timeout=20)
    for _ in range(60):
        time.sleep(0.5)
        try:
            raw = json.loads(out.read_text())
            break
        except ValueError:
            continue
    else:
        raise RuntimeError("calendar job gave no output (check Calendar access for ekctl)")
    out.unlink(missing_ok=True)
    return [e for e in raw if e.get("type") == "event"]


def events(days=7):
    skip = set(CFG["calendar_skip"])
    fixed = []
    if CFG.get("weekly_schedule"):  # the timetable, repeated every week
        import schedule
        fixed = schedule.events(CFG["weekly_schedule"], days=days)
    if CFG.get("calendar_ics"):  # iCal feeds: the way on Windows
        import ics_feed
        raw, errs = ics_feed.fetch(CFG["calendar_ics"], days=days)
        errors.extend(errs)
        return fixed + [e for e in raw if e.get("calendar") not in skip]
    if fixed and not EKCTL:
        return fixed
    if not EKCTL:  # no Calendar source configured
        return []
    today = dt.date.today()
    try:
        raw = json.loads(run([EKCTL, "events", "--from", today.isoformat(),
                              "--to", (today + dt.timedelta(days=days)).isoformat()]))
    except RuntimeError as e:
        if "denied" not in str(e).lower():
            raise
        raw = events_via_launchd()
    skip = set(CFG["calendar_skip"])
    return [{k: e.get(k) for k in ("title", "calendar", "start", "end", "allDay")}
            for e in raw if e.get("calendar") not in skip]


def github():
    prs, commits = [], {}
    fields = "repository,number,title,updatedAt,isDraft,url"
    for user in CFG["github_accounts"]:
        try:
            env = gh_env(user)
            for kind, flag in (("mine", "--author=@me"), ("review", "--review-requested=@me")):
                for p in json.loads(run(["gh", "search", "prs", flag, "--state=open", "--limit", "100",
                                         "--json", fields], env=env)):
                    prs.append({"kind": kind, "account": user, "repo": p["repository"]["nameWithOwner"],
                                "number": p["number"], "title": p["title"], "updated": p["updatedAt"][:10],
                                "draft": p["isDraft"], "url": p["url"]})
            for c in json.loads(run(["gh", "search", "commits", "--author=@me", "--sort", "committer-date",
                                     "--order", "desc", "--limit", "60", "--json", "repository,commit"], env=env)):
                repo = c["repository"]["fullName"]
                d = c["commit"]["committer"]["date"][:10]
                if d > commits.get(repo, ""):
                    commits[repo] = d
        except Exception as e:  # keep going with other accounts
            errors.append(f"GitHub ({user}): {e}")
    seen, uniq = set(), []
    for p in prs:
        key = (p["kind"], p["url"])
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq, commits


def vault():
    base = os.path.expanduser(CFG["vault_path"])
    out = {}
    if not os.path.isdir(base):  # no vault on this machine: nothing to read, not an error
        return out
    for lane, folders in CFG["vault_folders"].items():
        best = None
        ignore = tuple(CFG.get("vault_ignore_commits", []))
        for f in folders:
            log = run(["git", "-C", base, "log", "-15", "--format=%h %cs", "--", f], timeout=20).split("\n")
            d = next((ln.split()[1] for ln in log if ln.strip() and not ln.startswith(ignore)), None) if ignore \
                else next((ln.split()[1] for ln in log if ln.strip()), None)
            if d and (best is None or d > best[0]):
                best = (d, f)
        if best:
            out[lane] = {"date": best[0], "folder": best[1]}
    return out


def local_repos():
    """Last commit by you (git_author_emails, all branches) and newest uncommitted edit, per git repo under code_root."""
    base = os.path.expanduser(CFG["code_root"])
    skip = set(CFG.get("code_skip", []))
    authors = [f"--author={a}" for a in CFG.get("git_author_emails", [])]
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        depth = os.path.relpath(dirpath, base).count(os.sep)
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".venv", "venv", ".git") and not d.startswith(".")]
        if not (".git" in filenames or os.path.isdir(os.path.join(dirpath, ".git"))):
            if depth >= 3:
                dirnames[:] = []
            continue
        dirnames[:] = []
        rel = os.path.relpath(dirpath, base)
        if rel in skip:
            continue
        try:
            remote = run(["git", "-C", dirpath, "remote", "get-url", "origin"], timeout=10).strip()
        except Exception:
            remote = ""
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
        commit = ""
        try:
            commit = run(["git", "-C", dirpath, "log", "--all", "-1", "--format=%cs", *authors], timeout=20).strip()
        except Exception:
            pass
        edit = ""
        try:
            newest = 0
            for ln in run(["git", "-C", dirpath, "status", "--porcelain", "--untracked-files=normal"], timeout=20).splitlines():
                f = ln[3:].split(" -> ")[-1].strip('"')
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(dirpath, f)))
                except OSError:
                    pass
            if newest:
                edit = dt.date.fromtimestamp(newest).isoformat()
        except Exception:
            pass
        out.append({"path": rel, "repo": m.group(1) if m else None, "commit": commit or None, "edit": edit or None})
    return out


def safe(name, fn, default):
    try:
        return fn()
    except Exception as e:
        errors.append(f"{name}: {e}")
        return default


data = {"generated": dt.datetime.now().astimezone().isoformat(timespec="minutes")}
data["reminders"] = safe("Reminders", reminders, [])
data["events"] = safe("Calendar", events, [])
prs_commits = safe("GitHub", github, ([], {}))
data["prs"], data["commits"] = prs_commits
data["vault"] = safe("Vault", vault, {})
data["local_repos"] = safe("Local repos", local_repos, [])
data["errors"] = errors
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "local.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
print(f"reminders={len(data['reminders'])} events={len(data['events'])} prs={len(data['prs'])} "
      f"repos={len(data['commits'])} vault_lanes={len(data['vault'])} local_repos={len(data['local_repos'])} errors={len(errors)}")
for e in errors:
    print("ERROR", e)
