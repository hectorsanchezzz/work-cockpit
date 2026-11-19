#!/usr/bin/env python3
"""The cockpit's local server: serves out/ on 127.0.0.1:8765, plus three endpoints.

GET /api/settings returns what the settings page shows (see settings.py).
POST /api/settings saves any part of it, then rebuilds only what the change needs, under the same lock
as the 30-minute refresh: collect.py when a skip list changed, extras.py when a source was switched,
render_v2.py when config.json changed, and always proposals.py --live and build_local.py.

POST /api/reminder {"id", "action", "due"?, "title"?, "keep"?} acts on one open reminder through ekctl
(done, move, nodate, rename, cancel, think; see reminder_actions.py), logs it to logs/actions.log, patches
data/local.json and re-renders the page and the menu bar summary.

Requests must name the cockpit's own host; POSTs only from its own origin, as JSON. Linear, Calendar and GitHub stay read-only.
"""
import functools
import json
import os
import subprocess
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import reminder_actions as RA
import settings
import sources

ROOT = sources.ROOT
PY = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
PORT = 8765
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ORIGINS = {f"http://{h}" for h in HOSTS}
LOCK = "/tmp/cockpit-refresh.lock"
ENV = {**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + os.path.expanduser("~/bin")}


def skip_lists():
    return {s.lower() for s in json.loads((ROOT / "config.json").read_text()).get("reminder_skip_lists", [])}


def rebuild(before=None, extras=True, collect=False, render=False):
    for _ in range(180):  # wait up to 90 s for a running refresh
        try:
            os.mkdir(LOCK)
            break
        except FileExistsError:
            time.sleep(0.5)
    else:
        return False
    try:
        if before:
            before()
        steps = [["collect.py"]] * collect + [["extras.py"]] * extras + [["render_v2.py"]] * render
        for script in steps + [["proposals.py", "--live"], ["build_local.py"]]:
            subprocess.run([PY, *script], cwd=ROOT, env=ENV, capture_output=True, timeout=180)
        return True
    finally:
        os.rmdir(LOCK)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Host") not in HOSTS:  # a page on another site cannot read this one
            return self.reply(403, {"error": "forbidden"})
        if self.path == "/api/settings":
            return self.reply(200, settings.load())
        if self.path.startswith("/api/"):
            return self.reply(404, {"error": "not found"})
        return super().do_GET()

    def do_HEAD(self):
        if self.headers.get("Host") not in HOSTS:
            return self.reply(403, {"error": "forbidden"})
        return super().do_HEAD()

    def do_POST(self):
        if self.path not in ("/api/settings", "/api/reminder"):
            return self.reply(404, {"error": "not found"})
        if (self.headers.get("Host") not in HOSTS or self.headers.get("Origin") not in ORIGINS
                or not (self.headers.get("Content-Type") or "").startswith("application/json")):
            return self.reply(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(min(n, 16384 if self.path == "/api/settings" else 1024)))
            assert isinstance(body, dict)
        except (ValueError, AssertionError):
            return self.reply(400, {"error": "bad request"})
        if self.path == "/api/settings":
            try:
                changed = settings.save(body)
            except settings.Refused as e:
                return self.reply(400, {"error": str(e)})
            ok = True
            if changed:
                ok = rebuild(extras="sources" in changed, collect="skips" in changed, render="config" in changed)
            return self.reply(200 if ok else 503, {"ok": ok, "changed": sorted(changed)})
        try:
            done = RA.run(body, skip_lists())
        except RA.Refused as e:
            return self.reply(409 if "no longer" in str(e) else 400, {"error": str(e)})
        except Exception as e:
            RA.log(f"failed {body.get('action')} {body.get('id')} {str(e)[:120]}")
            return self.reply(502, {"error": "Reminders did not accept the change."})
        rebuild(before=lambda: RA.patch(done), extras=False, render=True)
        return self.reply(200, {"ok": True})


if __name__ == "__main__":
    handler = functools.partial(Handler, directory=str(ROOT / "out"))
    ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
