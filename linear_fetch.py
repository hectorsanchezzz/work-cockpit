#!/usr/bin/env python3
"""Read-only Linear fetch for the work cockpit, over Linear's GraphQL API.

The personal API key lives in the macOS Keychain (service "cockpit-linear").
It is read into memory for the requests only, never printed or written.
Writes data/linear.json in the same schema the renderer already reads.
On any failure the previous data/linear.json is kept and the error is
added to data/local.json so the page shows it. Only queries, no mutations.
"""
import datetime as dt
import json
import os
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.linear.app/graphql"
KEYCHAIN_SERVICE = "cockpit-linear"
# python.org Python ships without a CA store; use the macOS system bundle.
CAFILE = "/etc/ssl/cert.pem"
SSL_CTX = ssl.create_default_context(cafile=CAFILE if os.path.exists(CAFILE) else None)
ALEIX = "1337d284-41a6-4bed-8361-09157ff0e6f3"

QUERY = """
query($filter: IssueFilter, $after: String) {
  issues(filter: $filter, first: 100, after: $after, includeArchived: false) {
    pageInfo { hasNextPage endCursor }
    nodes { identifier title priority dueDate updatedAt state { name } project { name } }
  }
}
"""


def api_key():
    r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                       capture_output=True, text=True)
    key = r.stdout.strip()
    if r.returncode != 0 or not key:
        raise RuntimeError(f"no API key in Keychain (service {KEYCHAIN_SERVICE})")
    return key


def fetch(key, flt, cap=300):
    out, after = [], None
    while True:
        body = json.dumps({"query": QUERY, "variables": {"filter": flt, "after": after}}).encode()
        req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json", "Authorization": key})
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            data = json.loads(resp.read())
        if data.get("errors"):
            raise RuntimeError("; ".join(e.get("message", "error") for e in data["errors"])[:200])
        page = data["data"]["issues"]
        out += page["nodes"]
        if not page["pageInfo"]["hasNextPage"] or len(out) >= cap:
            return out
        after = page["pageInfo"]["endCursor"]


def row(n):
    proj = (n.get("project") or {}).get("name")
    return [n["identifier"], n["title"], (n.get("state") or {}).get("name"), proj,
            n.get("dueDate"), (n.get("updatedAt") or "")[:10], int(n.get("priority") or 0)]


def main():
    key = api_key()
    me = {"isMe": {"eq": True}}
    started = fetch(key, {"assignee": me, "state": {"type": {"eq": "started"}}})
    todo = fetch(key, {"assignee": me, "state": {"type": {"eq": "unstarted"}}})
    review = fetch(key, {"assignee": {"id": {"eq": ALEIX}}, "state": {"name": {"eq": "In Review"}}})
    del key
    data = {
        "generated": dt.datetime.now().astimezone().isoformat(timespec="minutes"),
        "aleix_review": [[n["identifier"], n["title"], (n.get("project") or {}).get("name"),
                          (n.get("updatedAt") or "")[:10], n.get("dueDate")] for n in review],
        "mine_started": [row(n) for n in started],
        "mine_todo": [row(n) for n in todo],
    }
    tmp = ROOT / "data" / "linear.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(ROOT / "data" / "linear.json")
    print(f"linear: aleix_review={len(review)} started={len(started)} todo={len(todo)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # keep the old snapshot, surface the error on the page
        msg = f"Linear: {type(e).__name__}: {e}"[:240]
        print("ERROR", msg, file=sys.stderr)
        lp = ROOT / "data" / "local.json"
        try:
            local = json.loads(lp.read_text())
            local.setdefault("errors", []).append(msg + " (showing the last good Linear snapshot)")
            lp.write_text(json.dumps(local, ensure_ascii=False))
        except Exception:
            pass
        sys.exit(0)
