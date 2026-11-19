#!/usr/bin/env python3
"""Render cockpit v1 (out/cockpit.html) from the shared model."""
from model import *  # noqa: F401,F403
import html
import datetime as dt
import re

# ---------- HTML ----------
def link(text, url):
    return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{text}</a>' if url else text


def row(idtxt, title, url, meta, meta_cls=""):
    idhtml = f'<span class="id">{clean(idtxt)}</span>' if idtxt else ""
    m = f'<span class="meta {meta_cls}">{clean(meta)}</span>' if meta else ""
    return f'<li>{link(idhtml + "<span class=t>" + clean(title) + "</span>", url)}{m}</li>'


def listing(items, render, first=4, empty="Nothing"):
    if not items:
        return f'<p class="empty">{empty}</p>'
    head = "".join(render(i) for i in items[:first])
    rest = items[first:]
    more = ""
    if rest:
        more = (f'<details><summary>{len(rest)} more</summary><ul>'
                + "".join(render(i) for i in rest) + "</ul></details>")
    return f"<ul>{head}</ul>{more}"


def event_row(e):
    start = e.get("start") or ""
    try:
        sd = dt.datetime.fromisoformat(start.replace(" ", "T"))
        when = sd.strftime("%a %d") + ("" if e.get("allDay") else sd.strftime(" %H:%M"))
    except ValueError:
        when = start[:16]
    return f'<li><span class="id">{clean(when)}</span><span class="t">{clean(e["title"])}</span></li>'


cards, quiet = [], []
tot_wait = tot_over = 0
for lane_cfg in CFG["lanes"]:
    k = lane_cfg["key"]
    L = lanes[k]
    L["waiting"].sort(key=lambda i: i.get("date") or "", reverse=True)
    L["overdue"].sort(key=lambda i: i.get("due") or "")
    touch = L["touch"]
    last = max(touch.values()) if touch else None
    last_age = age(last)
    stale = last_age is None or last_age > STALE
    stale_src = [f"{src} {fmt_age(age(v))}" for src, v in sorted(touch.items()) if (age(v) or 0) > STALE]
    if stale or stale_src:
        quiet.append((lane_cfg["name"], "all sources " + fmt_age(last_age) if stale else ", ".join(stale_src)))
    tot_wait += len(L["waiting"])
    tot_over += len(L["overdue"])
    chips = "".join(
        f'<span class="chip {"bad" if (age(v) or 0) > STALE else ""}">{src} {fmt_age(age(v))}</span>'
        for src, v in sorted(touch.items(), key=lambda kv: kv[1], reverse=True))
    budget = lane_cfg.get("hours_budget")
    budget_html = f'<span class="budget">{budget} h/week</span>' if budget not in (None, "") else ""
    na = next_actions(L)
    na_html = listing(na, lambda i: row(i["id"], i["title"], i["url"], f'{i["src"]}{" · " + i["meta"] if i["meta"] else ""}'),
                      first=3, empty="No open items")
    wait_html = listing(L["waiting"], lambda i: row(i["id"], i["title"], i["url"],
                        f'{i["kind"]} · {fmt_age(age(i["date"]))}',
                        "bad" if (age(i["date"]) or 0) > STALE else ""), empty="Nothing waiting on you")
    over_html = listing(L["overdue"], lambda i: row(i["id"] if i["kind"] == "Linear" else "", i["title"], i["url"],
                        f'{i["kind"]} · due {i["due"]}', "bad"), empty="Nothing overdue")
    ev = sorted(L["events"], key=lambda e: e.get("start") or "")
    ev_html = listing(ev, event_row, first=4, empty="No events in the next 7 days")
    open_count = len(L["started"]) + len(L["todo"])
    cards.append(f"""
<section class="card {'stale' if stale else ''}">
  <header>
    <h2>{clean(lane_cfg['name'])}</h2>
    {budget_html}
  </header>
  <div class="touch"><span class="lt {'bad' if stale else 'ok'}">Last touched {fmt_age(last_age)}</span>{chips}</div>
  <div class="counts"><span><b>{len(L['waiting'])}</b> waiting</span><span><b class="{'badtxt' if L['overdue'] else ''}">{len(L['overdue'])}</b> overdue</span><span><b>{open_count}</b> Linear open</span><span><b>{len(L['reminders'])}</b> reminders</span></div>
  <h3>Next 3</h3>{na_html}
  <h3>Waiting on me</h3>{wait_html}
  <h3>Overdue</h3>{over_html}
  <h3>Next 7 days</h3>{ev_html}
</section>""")

gen_local = LOCAL.get("generated", "")[:16].replace("T", " ")
gen_lin = LIN.get("generated", "")[:16].replace("T", " ")
quiet_html = ""
if quiet:
    quiet_html = ('<div class="quiet"><b>Gone quiet</b> ' + " · ".join(
        f"{clean(n)} ({clean(a)})" for n, a in quiet) + "</div>")
err_html = ""
if LOCAL.get("errors"):
    err_html = '<div class="errors">Source errors: ' + "; ".join(clean(e) for e in LOCAL["errors"]) + "</div>"

CSS = """
:root{--bg:#f6f6f3;--card:#ffffff;--ink:#1b1c1e;--mute:#6b6e75;--line:#e3e3de;--accent:#2f5bd3;
--bad:#c4321f;--badbg:#fbe9e6;--ok:#2e7d4f;--okbg:#e6f3eb;--chip:#efefea;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121315;--card:#1b1d20;--ink:#e8e8e6;
--mute:#9a9da4;--line:#2c2f34;--accent:#8aa8ff;--bad:#ff7a66;--badbg:#3a1d19;--ok:#6fcf97;--okbg:#17301f;--chip:#262a2f;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121315;--card:#1b1d20;--ink:#e8e8e6;--mute:#9a9da4;--line:#2c2f34;--accent:#8aa8ff;
--bad:#ff7a66;--badbg:#3a1d19;--ok:#6fcf97;--okbg:#17301f;--chip:#262a2f;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 "IBM Plex Sans",system-ui,-apple-system,sans-serif;
padding-inline:max(16px,env(safe-area-inset-left)) max(16px,env(safe-area-inset-right));padding-block:20px 40px}
.top{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 18px;margin:0 auto 14px;max-width:1400px}
h1{font-size:20px;margin:0;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:12px}
.tot{display:flex;gap:14px;font-size:13px}.tot b{font-variant-numeric:tabular-nums}
.quiet,.errors{max-width:1400px;margin:0 auto 14px;padding:8px 12px;border-radius:8px;background:var(--badbg);color:var(--bad);font-size:13px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(min(100%,360px),1fr));max-width:1400px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:0}
.card.stale{border-color:var(--bad);box-shadow:inset 3px 0 0 var(--bad)}
.card header{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
h2{font-size:16px;margin:0}
.budget{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
.touch{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.lt,.chip{font-size:11.5px;padding:2px 8px;border-radius:999px;font-variant-numeric:tabular-nums}
.lt.ok{background:var(--okbg);color:var(--ok);font-weight:600}.lt.bad{background:var(--badbg);color:var(--bad);font-weight:600}
.chip{background:var(--chip);color:var(--mute)}.chip.bad{color:var(--bad)}
.counts{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--mute);padding-bottom:8px;border-bottom:1px solid var(--line)}
.counts b{color:var(--ink);font-variant-numeric:tabular-nums}.badtxt{color:var(--bad)!important}
h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:12px 0 4px}
ul{list-style:none;margin:0;padding:0}
li{padding:4px 0;border-top:1px dashed var(--line);display:flex;flex-direction:column;gap:1px;min-width:0}
li:first-child{border-top:0}
li a{color:inherit;text-decoration:none}li a:hover .t{color:var(--accent);text-decoration:underline}
.id{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px;color:var(--accent);margin-right:6px;font-variant-numeric:tabular-nums}
.t{overflow-wrap:anywhere}
.meta{font-size:11.5px;color:var(--mute)}.meta.bad{color:var(--bad)}
.empty{color:var(--mute);font-size:12.5px;margin:2px 0}
details summary{cursor:pointer;color:var(--accent);font-size:12px;padding:4px 0}
footer{max-width:1400px;margin:18px auto 0;color:var(--mute);font-size:12px}
"""

page = f"""<title>Work Cockpit</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
<div class="top">
  <h1>Work Cockpit</h1>
  <span class="sub">Snapshot {clean(gen_local)} · Linear {clean(gen_lin)} · stale after {STALE} days</span>
  <span class="tot"><span><b>{tot_wait}</b> waiting on me</span><span><b>{tot_over}</b> overdue</span><span><b>{len(quiet)}</b> lanes with a quiet source</span></span>
</div>
{quiet_html}{err_html}
<div class="grid">{''.join(cards)}</div>
<footer>Read-only snapshot of Linear, Apple Reminders and Calendar, GitHub, the git repos under ~/development and the vault git log. Titles and IDs only. Lane mapping and hours budgets live in ~/development/cockpit/config.json.</footer>
"""
assert "—" not in page
(ROOT / "out").mkdir(exist_ok=True)
(ROOT / "out" / "cockpit.html").write_text(page)
print("wrote out/cockpit.html", len(page), "bytes; quiet:", [q[0] for q in quiet])
