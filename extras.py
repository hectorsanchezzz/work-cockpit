#!/usr/bin/env python3
"""Test sources for the cockpit, each behind its own toggle (sources.py). Writes data/extras.json.

GitHub pull requests: open PRs where your review is requested, and your own open PRs, per gh login.
The token is passed per call (GH_TOKEN from `gh auth token -u <login>`), never `gh auth switch`.
Blvck Sigma logins and repos only when their own toggle is on. Read only.

Rize tracked time: hours per project for this week (Monday to now) and last week, from the Rize GraphQL
API, mapped to lanes. The key is read from the Keychain (service cockpit-rize) per run, never stored,
printed or logged. Only per-lane totals are written; Rize project names stay out of extras.json.

Claude sessions (off by default): the Claude desktop app's local session files, read only. They are
undocumented, so any read failure becomes one quiet line. Kept per session: id, title, folder name, lane,
created and last activity. No transcript, prompt or report text. Scheduled-task runs and archived
sessions are left out.
"""
import datetime as dt
import glob
import json
import os
import ssl
import subprocess
import urllib.error
import urllib.request

import sources

ROOT = sources.ROOT
CFG = json.loads((ROOT / "config.json").read_text())
OUT = ROOT / "data" / "extras.json"
FIELDS = "repository,number,title,createdAt,updatedAt,isDraft,url"
RIZE_URL = "https://api.rize.io/api/v1/graphql"
_CA = "/etc/ssl/cert.pem"  # python.org Python on macOS ships without CA certs; Windows uses its own store
SSL_CTX = ssl.create_default_context(cafile=_CA if os.path.exists(_CA) else None)


def gh_env(user):
    import shutil
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI (gh) is not installed")
    r =subprocess.run(["gh", "auth", "token", "-u", user], capture_output=True, text=True, timeout=15)
    tok = r.stdout.strip()
    if not tok:
        raise RuntimeError("not signed in to gh")
    return {**os.environ, "GH_TOKEN": tok}


def search(flag, env):
    r = subprocess.run(["gh", "search", "prs", flag, "--state=open", "--limit", "100", "--json", FIELDS],
                       capture_output=True, text=True, timeout=60, env=env)
    if r.returncode:
        low = r.stderr.lower()
        raise RuntimeError("offline" if "connect" in low or "resolve" in low else "GitHub search failed")
    return json.loads(r.stdout)


def github_prs(include_bs):
    owners = CFG.get("github_owners", {})
    bs_accounts = set(CFG.get("github_bs_accounts", ["blvcksigma-app"]))
    accounts = [a for a in CFG["github_accounts"] if include_bs or a not in bs_accounts]
    items, errors, seen = [], [], set()
    for user in accounts:
        try:
            env = gh_env(user)
            for kind, flag in (("review", "--review-requested=@me"), ("mine", "--author=@me")):
                for p in search(flag, env):
                    repo = p["repository"]["nameWithOwner"]
                    lane = owners.get(repo.split("/")[0], "other")
                    if lane == "bs" and not include_bs:
                        continue
                    key = (kind, p["url"])
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append({"kind": kind, "lane": lane, "repo": repo, "number": p["number"],
                                  "title": p["title"], "created": p["createdAt"][:10],
                                  "updated": p["updatedAt"][:10], "draft": p["isDraft"], "url": p["url"]})
        except Exception as e:  # one quiet line per failing login, the rest keeps working
            errors.append(f"{user}: {e}")
    return {"items": items, "errors": errors}


def rize_key():
    from platform_util import secret
    return secret("cockpit-rize", "COCKPIT_RIZE_KEY")


def rize_query(key, query, variables):
    req = urllib.request.Request(RIZE_URL, data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                          "User-Agent": "work-cockpit"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:  # the message never includes the request, so the key cannot leak here
        raise RuntimeError("key refused" if e.code in (401, 403) else f"HTTP {e.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("offline") from None
    if body.get("errors"):
        raise RuntimeError("query refused")
    return body["data"]


def rize_lane(name):
    """Rize project name to lane: rize_projects, then linear_projects, then title_keywords. None if no rule matches."""
    if not name:
        return None
    for table in ("rize_projects", "linear_projects"):
        for k, lane in CFG.get(table, {}).items():
            if k.lower() == name.lower():
                return lane
    t = name.lower()
    for k, lane in CFG.get("title_keywords", {}).items():
        if k.lower() in t:
            return lane
    return None


RIZE_Q = """query($s: ISO8601DateTime!, $e: ISO8601DateTime!) {
  timeAllocation(startTime: $s, endTime: $e, groupBy: project) { totalDuration groups { totalDuration project { name } } }
}"""


def rize():
    key = rize_key()
    now = dt.datetime.now().astimezone()
    monday = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = {"this": (monday, now), "last": (monday - dt.timedelta(days=7), monday)}
    lanes = {l["key"] for l in CFG["lanes"]}
    out = {"items": [], "errors": [], "weeks": {}}
    for w, (s, e) in weeks.items():
        ta = rize_query(key, RIZE_Q, {"s": s.isoformat(), "e": e.isoformat()})["timeAllocation"]
        by = {"none": 0, "unmatched": 0}
        for g in ta.get("groups") or []:
            name = (g.get("project") or {}).get("name")
            lane = rize_lane(name)
            k = lane if lane in lanes else ("unmatched" if name else "none")
            by[k] = by.get(k, 0) + int(g.get("totalDuration") or 0)
        out["weeks"][w] = {"start": s.isoformat(timespec="minutes"), "end": e.isoformat(timespec="minutes"),
                           "total": int(ta.get("totalDuration") or 0), "seconds": by}
    for k in sorted(set(out["weeks"]["this"]["seconds"]) | set(out["weeks"]["last"]["seconds"])):
        out["items"].append({"lane": k, "this": out["weeks"]["this"]["seconds"].get(k, 0),
                             "last": out["weeks"]["last"]["seconds"].get(k, 0)})
    return out


_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~/Library/Application Support")
CLAUDE_GLOB = os.path.join(_APPDATA, "Claude", "claude-code-sessions", "*", "*", "local_*.json")
CLAUDE_DAYS = 7


def path_lane(cwd, title):
    """Folder to lane through code_path_keywords, then the title through title_keywords. None if nothing matches."""
    p = (cwd or "").lower()
    for k, lane in CFG.get("code_path_keywords", {}).items():
        if k.lower() in p:
            return lane
    t = (title or "").lower()
    for k, lane in CFG.get("title_keywords", {}).items():
        if k.lower() in t:
            return lane
    return None


def claude_sessions():
    files = glob.glob(CLAUDE_GLOB)
    if not files:
        raise RuntimeError("no session files found")
    cutoff = (dt.datetime.now().timestamp() - CLAUDE_DAYS * 86400) * 1000
    items, bad = [], 0
    for f in files:
        try:
            d = json.loads(open(f, encoding="utf-8").read())
            sid, last = d["sessionId"], int(d.get("lastActivityAt") or 0)
            assert isinstance(sid, str) and sid.startswith("local_")
        except (OSError, ValueError, KeyError, TypeError, AssertionError):
            bad += 1
            continue
        if d.get("isArchived") or d.get("scheduledTaskId") or last < cutoff:
            continue
        title = d.get("title") if isinstance(d.get("title"), str) else ""
        cwd = d.get("cwd") if isinstance(d.get("cwd"), str) else ""
        iso = lambda ms: dt.datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="minutes")
        items.append({"id": sid, "title": title, "folder": os.path.basename(cwd.replace("\\", "/").rstrip("/")), "lane": path_lane(cwd, title),
                      "side": bool(d.get("spawnedFrom")), "created": iso(int(d.get("createdAt") or last)), "last": iso(last)})
    items.sort(key=lambda x: x["last"], reverse=True)
    return {"items": items, "errors": [f"Claude sessions: {bad} files could not be read"] if bad > len(files) // 2 else [],
            "days": CLAUDE_DAYS}


def main():
    on = sources.load()
    try:
        prev = json.loads(OUT.read_text())
    except (OSError, ValueError):
        prev = {}
    out = {"generated": dt.datetime.now().astimezone().isoformat(timespec="minutes"), "sources": {}}
    if on["github_prs"]:
        try:
            out["sources"]["github_prs"] = github_prs(on["github_prs_bs"])
        except Exception as e:
            out["sources"]["github_prs"] = {"items": [], "errors": [f"GitHub: {e}"]}
    if on["rize"]:
        try:
            out["sources"]["rize"] = rize()
        except Exception as e:  # never str() a request here: only the messages raised above, which hold no key
            msg = str(e) if isinstance(e, RuntimeError) else type(e).__name__
            out["sources"]["rize"] = {"items": [], "errors": [f"Rize: {msg}"]}
    if on["claude_sessions"]:
        try:
            out["sources"]["claude_sessions"] = claude_sessions()
        except Exception as e:  # the files are undocumented: fail quietly, never with their content
            msg = str(e) if isinstance(e, RuntimeError) else type(e).__name__
            out["sources"]["claude_sessions"] = {"items": [], "errors": [f"Claude sessions: {msg}"]}
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1))
    tmp.replace(OUT)
    n = {k: len(v["items"]) for k, v in out["sources"].items()}
    print("extras:", n or "all test sources off", "(was", list(prev.get("sources", {})), ")")


if __name__ == "__main__":
    main()
