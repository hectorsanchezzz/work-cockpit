#!/usr/bin/env python3
"""Three visual proposals for the cockpit, rendered from the same data as the live page.

Writes out/proposals/a.html, b.html, c.html, d.html.
With --live it builds only D, without the switcher, into out/cockpit-d.html: that is the live page
(build_local.py turns it into out/index.html). Importing render_v2 also rewrites cockpit-v2.html and summary.json.
A  Private desk: time first. Porcelain light / deep ink dark, Bodoni date, today as a timeline with a gold "now" line.
B  Instrument:   lane first. Midnight instrument cluster, one band per lane with freshness gauges.
C  Agenda:       week first. A bound diary: forest cover, gold-foil date, ruled pages, ribbon on today.
D  Precision:    the Apple / Mercedes reading. System San Francisco only, aluminium light and black-glass dark,
                 a frosted local nav, Apple Calendar's red now-line, lanes as instrument rows with precise gauges.
Titles and IDs only. No em dashes.
"""
import re
import sys
import contextlib
import datetime as dt
import io
import json
import os
import subprocess

import settings as ST
import sources as SRC

with contextlib.redirect_stdout(io.StringIO()):
    import render_v2 as R  # builds the same data and components as the live page
from model import CFG, STALE, TODAY, age, clean, lanes, next_actions, ROOT  # noqa: F401

esc = R.esc
LANE_CFG = R.LANE_CFG
SHORT = R.SHORT
SOURCES = R.SOURCES
DAYS = R.DAYS
NOW = dt.datetime.now()
NOW_HM = NOW.strftime("%H:%M")
WEEKNO = TODAY.isocalendar()[1]
OUT = ROOT / "out" / "proposals"
OUT.mkdir(parents=True, exist_ok=True)

# The live page's component CSS (agenda, week, cards, chart) without its colour tokens,
# so each proposal can reuse the components under its own palette.
COMPONENTS = R.CSS[R.CSS.index("*{box-sizing"):]


# ---------- shared data ----------
def collect():
    cols = {"over": []}
    for dd in DAYS:
        cols[dd] = []
    for lc in LANE_CFG:
        k = lc["key"]
        L = lanes[k]
        for e in L["events"]:
            s = R.parse_dt(e.get("start"))
            if not s or s.date() not in cols:
                continue
            when = "" if e.get("allDay") else s.strftime("%H:%M")
            cols[s.date()].append({"lane": k, "kind": "ev", "when": when, "allday": bool(e.get("allDay")),
                                   "title": e["title"], "id": "", "url": None, "due": s.date()})
        for r in L["reminders"]:
            due = R.d(r.get("due"))
            if not due:
                continue
            it = {"lane": k, "kind": "rem", "when": str(r["due"])[11:16], "allday": False, "title": r["title"],
                  "id": "", "url": None, "due": due, "recurring": r.get("recurring"),
                  "rid": r.get("id"), "list": r.get("list")}
            if due < TODAY:
                cols["over"].append(it)
            elif due in cols:
                cols[due].append(it)
        for i in L["started"] + L["todo"]:
            due = R.d(i.get("due"))
            if not due:
                continue
            it = {"lane": k, "kind": "lin", "when": "", "allday": False, "title": i["title"], "id": i["id"],
                  "url": i["url"], "due": due}
            if due < TODAY:
                cols["over"].append(it)
            elif due in cols:
                cols[due].append(it)
    for key in cols:
        if key == "over":
            cols[key].sort(key=lambda i: (i["due"], i["lane"]), reverse=True)
        else:
            cols[key].sort(key=lambda i: (i["when"] or ("00" if i["allday"] else "99"), i["lane"]))
    return cols


COLS = collect()


def _think_list():
    """The Reminders list called Think (any case), or None. Needs thinking works only when it exists."""
    try:
        from platform_util import EKCTL
        if not EKCTL:
            return None
        r = subprocess.run([EKCTL, "lists"], capture_output=True, text=True, timeout=10)
        return next((x["title"] for x in json.loads(r.stdout) if (x.get("title") or "").lower() == "think"), None)
    except (OSError, ValueError, subprocess.SubprocessError, TypeError, KeyError, AttributeError):
        return None


THINK = _think_list() if "--live" in sys.argv else None
# Reminders parked in Think, under the lane of the list they came from (model.py maps them by "from").
THINK_ITEMS = [{"lane": lc["key"], "kind": "rem", "when": "", "allday": False, "title": r["title"], "id": "", "url": None, "due": None,
                "recurring": r.get("recurring"), "rid": r.get("id"), "list": r.get("list")}
               for lc in LANE_CFG for r in lanes[lc["key"]]["reminders"]
               if not r.get("due") and (r.get("list") or "").lower() == "think" and r.get("id")]


def hours(k):
    h = 0.0
    for e in lanes[k]["events"]:
        s, en = R.parse_dt(e.get("start")), R.parse_dt(e.get("end"))
        if s and en and en > s and not e.get("allDay") and s.date() in DAYS:
            h += (en - s).total_seconds() / 3600
    return h


def info(lc):
    k = lc["key"]
    L = lanes[k]
    t = L["touch"]
    ages = {s: (age(t[s]) if s in t else None) for s in SOURCES}
    known = [a for a in ages.values() if a is not None]
    last = min(known) if known else None
    stale_src = [s for s, a in ages.items() if a is not None and a > STALE]
    state = "quiet" if last is None or last > STALE else ("partial" if stale_src else "active")
    return {"key": k, "name": lc["name"], "short": SHORT.get(k, lc["name"]), "ages": ages, "last": last,
            "state": state, "stale_src": stale_src, "waiting": L["waiting"], "overdue": L["overdue"],
            "open": len(L["started"]) + len(L["todo"]), "na": next_actions(L), "hours": hours(k),
            "budget": lc.get("hours_budget")}


INFO = [info(lc) for lc in LANE_CFG]
TOT_WAIT = sum(len(i["waiting"]) for i in INFO)
TOT_OVER = sum(len(i["overdue"]) for i in INFO)
QUIET = sum(1 for i in INFO if i["state"] != "active")


def ago(n):
    return "never" if n is None else ("today" if n <= 0 else f"{n}d")


def state_word(i):
    if i["state"] == "quiet":
        return f"Quiet {ago(i['last'])}"
    if i["state"] == "partial":
        return f"{', '.join(i['stale_src'])} quiet"
    return f"Active {ago(i['last'])}"


ACT = False  # set by build_d on the live page: reminders get Done and a menu of actions
MORE_SVG = ('<svg width="15" height="15" viewBox="0 0 15 15" aria-hidden="true"><circle cx="3" cy="7.5" r="1.3"/>'
            '<circle cx="7.5" cy="7.5" r="1.3"/><circle cx="12" cy="7.5" r="1.3"/></svg>')


def item(it, late=False, lane_tag=True):
    """One dated item. Every proposal styles the same markup its own way."""
    k = it["lane"]
    if ACT and it["kind"] == "rem" and it.get("rid"):
        return act_item(it, late, lane_tag)
    if it["kind"] == "ev":
        lead = f'<span class="w">{"all day" if it["allday"] else clean(it["when"])}</span>'
    elif it["kind"] == "rem":
        lead = '<span class="ico rem" aria-label="Reminder"></span>' + (f'<span class="w">{clean(it["when"])}</span>' if it["when"] else "")
    else:
        lead = f'<span class="ico lin" aria-label="Linear"></span><span class="iid">{clean(it["id"])}</span>'
    body = f'{lead}<span class="tt">{clean(it["title"])}</span>'
    if it["url"]:
        body = f'<a href="{esc(it["url"])}" target="_blank" rel="noopener">{body}</a>'
    tail = ""
    if lane_tag:
        tail += f'<span class="lt">{clean(SHORT.get(k, k))}</span>'
    if late:
        tail += f'<span class="late">{(TODAY - it["due"]).days}d late</span>'
    if it.get("recurring"):
        tail += '<span class="rep">repeats</span>'
    past = " past" if (it["kind"] == "ev" and it["when"] and it["due"] == TODAY and it["when"] < NOW_HM) else ""
    attrs = f' data-due="{it["due"].isoformat()}"' if it.get("due") else ""
    if it["url"]:
        attrs += f' data-url="{esc(it["url"])}"'
    return f'<li class="it l-{k} k-{it["kind"]}{past}"{attrs}>{body}{tail}</li>'


def act_item(it, late, lane_tag):
    """A reminder the page can act on: a Done ring, the title, and a menu (move, no date, rename, cancel)."""
    k, t = it["lane"], clean(it["title"])
    attrs = f' data-rid="{esc(it["rid"])}" data-due="{it["due"].isoformat() if it.get("due") else ""}" data-when="{esc(it["when"])}"'
    if it.get("recurring"):
        attrs += ' data-rec="1"'
    if t != esc(it["title"]):
        attrs += " data-norename"
    lead = f'<button class="ck" type="button" aria-label="Mark done: {t}"><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="5.25"/><path d="M3.6 6.1l1.6 1.6 3.2-3.3"/></svg></button>'
    if it["when"]:
        lead += f'<span class="w">{clean(it["when"])}</span>'
    tail = f'<span class="lt">{clean(SHORT.get(k, k))}</span>' if lane_tag else ""
    if late:
        tail += f'<span class="late">{(TODAY - it["due"]).days}d late</span>'
    if it.get("recurring"):
        tail += '<span class="rep">repeats</span>'
    if tail:
        tail = f'<span class="tail">{tail}</span>'
    tail += f'<button class="mo" type="button" aria-haspopup="menu" aria-expanded="false" aria-label="Actions: {t}">{MORE_SVG}</button>'
    return f'<li class="it l-{k} k-rem act"{attrs}>{lead}<span class="tt">{t}</span>{tail}</li>'


def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (t or "").lower())).strip()


DUP_STOP = set("a an the to of for on in at by and or with if is be from vs de la el los las del en y i per amb que con para al un una".split())


def dups_block(first=3):
    """Open reminders that look like the same task, across all lanes. Two ways to match:
    nearly the same title (difflib ratio over 0.8) with the same numbers in it, so '1M net worth' and
    '5M net worth' stay apart; or the same due day and at least 3 shared words (stopwords left out)
    making up 40% of the shorter title, which catches two wordings of one deadline."""
    import difflib
    rs = [(lc["key"], r, norm(r.get("title"))) for lc in LANE_CFG for r in lanes[lc["key"]]["reminders"] if r.get("id")]
    rs = [x for x in rs if x[2]]
    words = {id(x): {w for w in x[2].split() if len(w) > 1 and w not in DUP_STOP} for x in rs}
    nums = {id(x): {w for w in x[2].split() if any(c.isdigit() for c in w)} for x in rs}
    day = {id(x): (x[1].get("due") or "")[:10] for x in rs}
    pairs = []
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            a, b = rs[i], rs[j]
            m = difflib.SequenceMatcher(None, a[2], b[2])
            if nums[id(a)] == nums[id(b)] and m.real_quick_ratio() > 0.8 and m.quick_ratio() > 0.8 and m.ratio() > 0.8:
                pairs.append((1, a, b))
            elif day[id(a)] and day[id(a)] == day[id(b)]:
                wa, wb = words[id(a)], words[id(b)]
                shared = len(wa & wb)
                if shared >= 3 and shared / min(len(wa), len(wb)) >= 0.4:
                    pairs.append((0, a, b))
    if not pairs:
        return ""
    pairs.sort(key=lambda p: (p[0], day[id(p[1])] or "9999"))

    def side(x, other):
        k, r, _ = x
        due = R.d(r.get("due"))
        when = ("No date" if not due else f"{(TODAY - due).days}d late" if due < TODAY else f"Due {due.day} {due.strftime('%b')}")
        return (f'<div class="dq l-{k}" data-rid="{esc(r["id"])}"><span class="tt">{clean(r.get("title"))}</span>'
                f'<span class="meta"><span class="ln">{clean(SHORT.get(k, k))}</span><span class="{"bad" if due and due < TODAY else ""}">{when}</span>'
                f'<button class="keep" type="button" data-keep="{esc(r["id"])}" data-drop="{esc(other[1]["id"])}">Keep</button></span></div>')

    def li(p):
        _, a, b = p
        return f'<li class="dp" data-a="{esc(a[1]["id"])}" data-b="{esc(b[1]["id"])}">{side(a, b)}{side(b, a)}</li>'
    rest = pairs[first:]
    more = (f'<details><summary>{len(rest)} more</summary><ul>{"".join(li(p) for p in rest)}</ul></details>' if rest else "")
    return (f'<div class="block dupb" id="dups"><div class="sec"><h2>Possible duplicates</h2>'
            f'<p>Keep one and the other is cancelled, noting which it duplicated.</p></div>'
            f'<section class="tile dups"><ul>{"".join(li(p) for p in pairs[:first])}</ul>{more}</section></div>')


def listing(items, first, late=False, lane_tag=True, cls="its"):
    if not items:
        return '<p class="empty">Nothing</p>'
    head = "".join(item(i, late, lane_tag) for i in items[:first])
    rest = items[first:]
    more = (f'<details><summary>{len(rest)} more</summary><ul class="{cls}">{"".join(item(i, late, lane_tag) for i in rest)}</ul></details>' if rest else "")
    return f'<ul class="{cls}">{head}</ul>{more}'


def cards(order=None):
    out = []
    for lc in (order or LANE_CFG):
        k = lc["key"]
        html_ = R.card(lc).replace(f'<section class="card l-{k}">', f'<section class="card l-{k}" id="lane-{k}">', 1)
        i = next(x for x in INFO if x["key"] == k)
        src = " · ".join(f'<span class="{"bad" if (a is not None and a > STALE) else ""}">{s} {ago(a)}</span>' for s, a in i["ages"].items())
        html_ = html_.replace('<div class="stats">', f'<p class="srcages">Last touched: {src}</p><div class="stats">', 1)
        out.append(html_)
    return "".join(out)


def switcher(cur):
    links = [("d", "Precision"), ("a", "Private desk"), ("b", "Instrument"), ("c", "Agenda")]
    a = "".join(f'<a href="{x}.html"{" aria-current=page" if x == cur else ""}>{lbl}</a>' for x, lbl in links)
    return f'<nav class="switch" aria-label="Proposals">{a}<a href="../">Live</a><a href="../cockpit-v2.html">v2</a></nav>'


SWITCH_CSS = """
.switch{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);display:flex;gap:2px;padding:5px;border-radius:999px;background:rgba(12,14,18,.8);
backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);border:1px solid rgba(255,255,255,.09);
box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 12px 32px rgba(0,0,0,.35);z-index:9;max-width:calc(100vw - 24px);overflow-x:auto;scrollbar-width:none}
.switch a{font:500 12px/1 -apple-system,system-ui,sans-serif;letter-spacing:.01em;color:#B9BDC6;padding:9px 14px;border-radius:999px;white-space:nowrap;text-decoration:none;transition:color .2s}
.switch a:hover{color:#fff}
.switch a[aria-current]{background:linear-gradient(180deg,#F4ECD8,#D8C597);color:#17140E;box-shadow:0 1px 0 rgba(255,255,255,.5) inset}
.switch a:focus-visible{outline:2px solid #D8C597;outline-offset:2px}
body{padding-bottom:88px!important}
"""


def FONTS(fonts):
    if not fonts:
        return ""  # D uses the Mac's own San Francisco, nothing to load
    return ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?{fonts}&display=swap" rel="stylesheet">')


LIVE = "--live" in sys.argv


def page(cur, title, fonts, css, body):
    if LIVE:
        doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Work Cockpit v2</title>
<style>{COMPONENTS}{css}</style></head><body>{body}</body></html>"""
        assert "\u2014" not in doc
        tmp = ROOT / "out" / "cockpit-d.html.tmp"
        tmp.write_text(doc)
        tmp.replace(ROOT / "out" / "cockpit-d.html")
        return
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cockpit proposal {cur.upper()}, {title}</title>
{FONTS(fonts)}
<style>{COMPONENTS}{css}{SWITCH_CSS}</style></head><body>{body}{switcher(cur)}</body></html>"""
    assert "—" not in doc
    (OUT / f"{cur}.html").write_text(doc)


GEN = R.gen_local
TALLY = (f'<b class="bad">{TOT_OVER}</b> overdue', f'<b>{TOT_WAIT}</b> waiting on you', f'<b>{QUIET}</b> of {len(INFO)} lanes quiet')


# =====================================================================
# A. Today desk
# =====================================================================
A_CSS = """
:root{--bg:#EDEFF1;--panel:#FCFCFD;--ink:#14171C;--mute:#6A707A;--line:#E0E3E7;--soft:#F4F5F7;--accent:#8A6A34;--gold:#B08D4F;
--bad:#A8432F;--badbg:#F6E9E5;--warn:#966A1E;--warnbg:#F5EEDF;--ok:#3B7356;--okbg:#E6EFE9;--zone:rgba(168,67,47,.06);
--axis:#4F6FA8;--bs:#7D838E;--delvion:#3F8C80;--pbe:#9C5B80;--tfg:#B0843A;--personal:#64844F;
--sh:0 1px 1px rgba(20,24,32,.03),0 2px 6px -2px rgba(20,24,32,.05),0 22px 44px -28px rgba(20,24,32,.22);
--disp:"Bodoni Moda",Didot,serif;--sans:"Instrument Sans",system-ui,sans-serif;--mono:"Geist Mono",ui-monospace,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0C0F14;--panel:#13171E;--ink:#ECE8E0;--mute:#8B919B;--line:#222833;--soft:#191E27;--accent:#CDB27A;--gold:#CDB27A;
--bad:#E27E6A;--badbg:#2D1B18;--warn:#D9AC5E;--warnbg:#2C2416;--ok:#7DBE98;--okbg:#16261E;--zone:rgba(226,126,106,.07);
--axis:#8EA6D6;--bs:#A7ACB5;--delvion:#79C1B5;--pbe:#CF92B4;--tfg:#D8B06A;--personal:#9DBB86;
--sh:0 1px 0 rgba(255,255,255,.035) inset,0 24px 48px -28px rgba(0,0,0,.7);color-scheme:dark}}
body{font-size:14px;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{gap:28px;max-width:1320px}
/* masthead */
.hd{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:24px 48px;padding:30px 0 30px;border-bottom:1px solid var(--line)}
.eyebrow{font:500 10.5px var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--mute);margin:0 0 20px;display:flex;align-items:center;gap:12px}
.eyebrow::before{content:"";width:24px;height:1px;background:var(--gold)}
.hd h1{font:400 clamp(46px,6.6vw,88px)/.92 var(--disp);letter-spacing:-.025em;margin:0}
.hd h1 em{font-style:italic}
.hd h1 span{color:var(--mute);margin-left:.22em}
.tally{display:flex;margin:0;padding-bottom:8px}
.tally>*{display:flex;flex-direction:column;gap:10px;padding-left:28px;margin-left:28px;border-left:1px solid var(--line);font:500 10px var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--mute)}
.tally>*:first-child{border-left:0;margin-left:0;padding-left:0}
.tally b{font:400 42px/1 var(--disp);letter-spacing:-.02em;color:var(--ink);text-transform:none}
.tally b.bad{color:var(--bad)}
/* surfaces */
.sheet,.panel,.card{background:var(--panel);border:1px solid var(--line);border-radius:20px;box-shadow:var(--sh)}
.sheet{padding:28px 30px}
.panel{padding:26px 30px}
.sheet>h2,.panel>h2{font:500 10.5px var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--mute);margin:0 0 20px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.sheet>h2 b{font:italic 400 22px/1 var(--disp);letter-spacing:0;color:var(--ink)}
.panel>h2 em{font:italic 400 15px var(--disp);letter-spacing:0;text-transform:none;color:var(--mute);margin:0}
.main{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:24px;align-items:start}
/* today */
.tl,.its{list-style:none;margin:0;padding:0}
.it>a{display:contents}
.it>a:hover .tt{color:var(--accent)}
.tl .it{display:flex;gap:16px;align-items:baseline;padding:14px 0;border-top:1px solid var(--line);font-size:15.5px;line-height:1.4}
.tl>.it:first-child,.tl>.anytime+.it,.now+.it{border-top:0}
.it .w{font:400 12px var(--mono);color:var(--mute);min-width:62px;flex:none;font-variant-numeric:tabular-nums}
.it .ico{flex:none;width:9px;height:9px;display:inline-block;align-self:center}
.ico.rem{border:1.5px solid var(--lc);border-radius:50%}
.ico.lin{border:1.5px solid var(--lc);border-radius:1px;transform:rotate(45deg) scale(.82)}
.it .iid{font:500 11.5px var(--mono);color:var(--accent);flex:none}
.it .tt{flex:1;min-width:0;overflow-wrap:anywhere;transition:color .2s}
.it .lt{flex:none;display:inline-flex;align-items:center;gap:7px;font:500 10px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}
.it .lt::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--lc)}
.it .late{flex:none;font:500 11px var(--mono);color:var(--bad);font-variant-numeric:tabular-nums}
.it .rep{flex:none;font:italic 400 13px var(--disp);color:var(--mute)}
.tl .it.past{opacity:.4}
.tl .k-rem .w,.tl .k-lin .iid{min-width:0}
.tl .anytime{font:500 10px var(--mono);color:var(--mute);text-transform:uppercase;letter-spacing:.18em;padding:0 0 6px}
.now{display:flex;align-items:center;gap:12px;padding:8px 0;color:var(--gold);font:500 10px var(--mono);letter-spacing:.18em;text-transform:uppercase}
.now::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--gold);box-shadow:0 0 0 4px color-mix(in srgb,var(--gold) 16%,transparent)}
.now::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--gold),transparent)}
.carried{margin-top:28px;border-top:1px solid var(--line);padding-top:22px}
.carried h3{font:500 10.5px var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--bad);margin:0 0 10px}
.its .it{display:flex;gap:10px;align-items:baseline;padding:9px 0;border-top:1px solid var(--line);font-size:13.5px}
.its .it:first-child{border-top:0}
/* lanes */
.lanes{display:flex;flex-direction:column}
.lr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 14px;padding:16px 0;border-top:1px solid var(--line);color:inherit;text-decoration:none}
.lr:first-child{border-top:0;padding-top:2px}
.lr .nm{display:flex;align-items:center;gap:12px;font:400 23px/1.1 var(--disp);letter-spacing:-.01em;transition:color .2s}
.lr .nm::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--lc);flex:none}
.lr.quiet .nm::before{background:none;box-shadow:inset 0 0 0 1.5px var(--lc)}
.lr:hover .nm{color:var(--accent)}
.lr .st{border:0;padding:0;background:none;justify-self:end;align-self:center;font:500 10px var(--mono);letter-spacing:.14em;text-transform:uppercase}
.lr.active .st{color:var(--ok)}.lr.partial .st{color:var(--warn)}.lr.quiet .st{color:var(--bad)}
.lr .src{grid-column:1;padding-left:19px;font:400 11px var(--mono);color:var(--mute);display:flex;gap:12px;flex-wrap:wrap}
.lr .src .bad{color:var(--bad)}
.lr .cnt{grid-column:2;justify-self:end;font:400 11px var(--mono);color:var(--mute);white-space:nowrap}
/* next six days */
.six{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:24px}
.dcol h3{margin:0 0 12px;padding-bottom:10px;border-bottom:1px solid var(--line);font:500 10px var(--mono);color:var(--mute);letter-spacing:.18em;text-transform:uppercase;display:flex;gap:8px;align-items:baseline}
.dcol h3 b{font:400 28px/1 var(--disp);color:var(--ink);letter-spacing:-.02em;text-transform:none}
.dcol .its .it{display:block;font-size:13px;line-height:1.4;border-top:0;padding:3px 0 3px 11px;margin-bottom:8px;border-left:1.5px solid var(--lc)}
.dcol .it .w,.dcol .it .iid{display:block;min-width:0;font-size:10.5px;margin-bottom:1px}
.dcol .it .ico{margin-right:6px}
.dcol .it .rep,.dcol .it .late{margin-left:6px}
.dcol .its .it .lt{display:none}
.empty{font:italic 400 15px var(--disp);color:var(--mute);margin:0}
details summary{font:500 10px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--accent);padding:10px 0 2px;list-style:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"+ "}
details[open] summary::before{content:"- "}
/* lane cards */
.grid{gap:24px;grid-template-columns:repeat(auto-fill,minmax(min(100%,400px),1fr))}
.card{position:relative;padding:26px 28px 24px;border-top:1px solid var(--line)}
.card::before{content:"";position:absolute;top:-1px;left:28px;width:36px;height:2px;background:var(--lc)}
.card h2{font:400 28px/1.05 var(--disp);letter-spacing:-.015em}
.card h2 .dot{display:none}
.pill{background:none!important;padding:0;border-radius:0;font:500 10px var(--mono);letter-spacing:.14em;text-transform:uppercase;display:inline-flex;align-items:center;gap:8px}
.pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.srcages{font:400 11px var(--mono);color:var(--mute);margin:12px 0 0;line-height:1.6}
.srcages .bad{color:var(--bad)}
.stats{gap:0;margin:20px 0 4px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.st{background:none;border-radius:0;padding:14px 0 14px 16px;border-left:1px solid var(--line)}
.st:first-child{border-left:0;padding-left:0}
.st b{font:400 32px/1 var(--disp);letter-spacing:-.02em;margin-bottom:8px}
.st span{font:500 9.5px var(--mono);letter-spacing:.14em;text-transform:uppercase}
.card h3{font:500 10px var(--mono);letter-spacing:.18em;color:var(--mute);margin:22px 0 6px}
.h3n{font:italic 400 13px var(--disp);letter-spacing:0;text-transform:none}
.na li{padding:9px 0 9px 26px;border-top:1px solid var(--line)}
.na li::before{background:none;color:var(--gold);font:italic 400 17px/1 var(--disp);width:auto;height:auto;top:10px;text-align:left}
.ar{padding:9px 0;border-top:1px solid var(--line)}
.mini{height:2px;border-radius:1px;background:var(--line)}
.id{color:var(--accent);font-size:11px}
/* hours */
.wk{border-top:1px solid var(--line)}
.wk>div{padding:10px 8px}
.wk-h{font:500 10px var(--mono);letter-spacing:.14em}
.wk-h b{font:400 24px/1.1 var(--disp);letter-spacing:-.01em;margin-top:2px}
.wk-name{font:400 17px var(--disp)}
.wk-name .dot{width:6px;height:6px}
.ev{background:var(--soft);border-left:1.5px solid var(--lc);border-radius:3px;padding:4px 7px}
.plan b{font:400 20px var(--disp)}
.meter{height:2px;border-radius:1px;background:var(--line)}
@media (max-width:1060px){.main{grid-template-columns:1fr}.six{grid-template-columns:repeat(3,minmax(0,1fr))}.hd{grid-template-columns:1fr}}
@media (max-width:600px){.sheet,.panel{padding:22px 18px}.card{padding:22px 18px}.card::before{left:18px}.six{grid-template-columns:1fr 1fr;gap:20px}
.tally>*{padding-left:16px;margin-left:16px}.tally b{font-size:30px}.tl .it{flex-wrap:wrap;gap:4px 12px}.it .lt{order:5}.hd{padding-top:12px}}
@media (prefers-reduced-motion:no-preference){.wrap>*{animation:rise .7s cubic-bezier(.2,.7,.1,1) both}.wrap>*:nth-child(2){animation-delay:.06s}.wrap>*:nth-child(n+3){animation-delay:.12s}
@keyframes rise{from{opacity:0;transform:translateY(8px)}}
.now::before{animation:pulse 3s ease-in-out infinite}@keyframes pulse{50%{box-shadow:0 0 0 7px color-mix(in srgb,var(--gold) 6%,transparent)}}}
"""


def build_a():
    today = COLS[TODAY]
    anytime = [i for i in today if not i["when"]]
    timed = [i for i in today if i["when"]]
    rows = []
    if anytime:
        rows.append('<li class="anytime">Any time today</li>' + "".join(item(i) for i in anytime))
    placed = False
    for i in timed:
        if not placed and i["when"] >= NOW_HM:
            rows.append(f'<li class="now">now {NOW_HM}</li>')
            placed = True
        rows.append(item(i))
    if not placed:
        rows.append(f'<li class="now">now {NOW_HM}</li>')
    over = COLS["over"]
    lanes_html = "".join(
        f'<a class="lr l-{i["key"]} {i["state"]}" href="#lane-{i["key"]}"><span class="nm">{clean(i["short"])}</span>'
        f'<span class="st">{clean(state_word(i))}</span>'
        f'<span class="src">{"".join(f"<span class={chr(34)}{"bad" if a is not None and a > STALE else ""}{chr(34)}>{s} {ago(a)}</span>" for s, a in i["ages"].items())}</span>'
        f'<span class="cnt">{len(i["waiting"])} waiting · {len(i["overdue"])} overdue</span></a>'
        for i in INFO)
    six = "".join(f'<div class="dcol"><h3>{dd.strftime("%a")}<b>{dd.day}</b></h3>{listing(COLS[dd], 6, lane_tag=False)}</div>' for dd in DAYS[1:])
    body = f"""<div class="wrap">
<header class="hd"><div><p class="eyebrow">Work Cockpit · week {WEEKNO} · snapshot {clean(GEN[11:])}</p>
<h1><em>{TODAY.strftime("%A")}</em> <span>{TODAY.day} {TODAY.strftime("%B")}</span></h1></div>
<p class="tally"><a href="#carried" style="color:inherit;text-decoration:none">{TALLY[0]}</a><span>{TALLY[1]}</span><span>{TALLY[2]}</span></p></header>
<div class="main">
<section class="sheet"><h2>Today <b>{len(today)}</b></h2><ol class="tl">{"".join(rows)}</ol>
<div class="carried" id="carried"><h3>Carried over · {len(over)}</h3>{listing(over, 6, late=True)}</div></section>
<section class="sheet"><h2>Lanes</h2><div class="lanes">{lanes_html}</div></section>
</div>
<section class="sheet"><h2>Next six days</h2><div class="six">{six}</div></section>
<div class="grid">{cards()}</div>
<section class="panel"><h2>Hours by lane<em>next 7 days of calendar, booked against budget</em></h2>{R.week()}</section>
</div>"""
    page("a", "Private desk", "family=Bodoni+Moda:ital,opsz,wght@0,6..96,400;0,6..96,500;1,6..96,400&family=Instrument+Sans:wght@400;500;600&family=Geist+Mono:wght@400;500", A_CSS, body)


# =====================================================================
# B. Lane bands
# =====================================================================
B_CSS = """
:root{--bg:#08090D;--panel:#0F1218;--ink:#E6E8ED;--mute:#7C8392;--line:#1D222C;--soft:#151922;--accent:#D6BE8A;
--bad:#E8806E;--badbg:#2A1715;--warn:#E2B266;--warnbg:#2A2113;--ok:#88C9A5;--okbg:#13241B;--zone:rgba(232,128,110,.06);
--axis:#93A6DA;--bs:#AAB0BB;--delvion:#7EC6BB;--pbe:#D49ABD;--tfg:#E0B872;--personal:#A6C38D;
--surface:linear-gradient(180deg,#11141B,#0D1015);--rim:inset 0 1px 0 rgba(255,255,255,.035);
--sans:"Archivo",system-ui,sans-serif;--mono:"DM Mono",ui-monospace,monospace;color-scheme:dark}
body{background:radial-gradient(1400px 700px at 75% -20%,#161B27 0,transparent 65%),radial-gradient(900px 500px at -10% 110%,#10131B 0,transparent 60%),#08090D;background-attachment:fixed;-webkit-font-smoothing:antialiased;font-size:13.5px}
.wrap{max-width:1440px;gap:18px}
/* header: the readouts are the hero */
.bar{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:20px 28px;padding:18px 0 24px;border-bottom:1px solid var(--line)}
.mark{display:flex;flex-direction:column;gap:12px;font:600 12px/1 var(--sans);font-stretch:125%;letter-spacing:.34em;text-transform:uppercase}
.mark span{font:400 12px var(--mono);letter-spacing:.04em;text-transform:none;color:var(--mute)}
.seg{display:flex}
.seg>*{display:flex;flex-direction:column-reverse;gap:10px;padding-left:30px;margin-left:30px;border-left:1px solid var(--line);font:600 9.5px var(--sans);font-stretch:125%;letter-spacing:.22em;text-transform:uppercase;color:var(--mute);text-decoration:none}
.seg>*:first-child{border-left:0;margin-left:0;padding-left:0}
.seg b{font:300 48px/.9 var(--mono);letter-spacing:-.04em;color:var(--ink);text-transform:none}
.seg b.bad{color:var(--bad);text-shadow:0 0 28px color-mix(in srgb,var(--bad) 35%,transparent)}
/* today strip */
.ribbon{display:flex;gap:10px;align-items:stretch;overflow-x:auto;padding:2px 0 6px;scrollbar-width:none}
.ribbon .lbl{flex:none;display:flex;align-items:center;padding-right:8px;font:600 10px var(--sans);font-stretch:125%;letter-spacing:.26em;text-transform:uppercase;color:var(--accent)}
.ribbon ul{display:flex;gap:8px;list-style:none;margin:0;padding:0}
.ribbon .it{flex:none;max-width:280px;display:flex;gap:8px;align-items:center;padding:9px 14px;border-radius:10px;background:var(--surface);border:1px solid var(--line);box-shadow:var(--rim);font-size:12.5px}
.ribbon .it::before{content:"";flex:none;width:6px;height:6px;border-radius:50%;background:var(--lc)}
.ribbon .it .tt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ribbon .it.past{opacity:.45}
.ribbon .lt{display:none}
.ribbon .carry{flex:none;align-self:center;font:400 11px var(--mono);color:var(--bad);border:1px solid color-mix(in srgb,var(--bad) 40%,transparent);border-radius:10px;padding:9px 14px;text-decoration:none}
.it>a{display:contents}
.w{font:400 11px var(--mono);color:var(--mute);flex:none;font-variant-numeric:tabular-nums}
.ico{flex:none;width:8px;height:8px;display:inline-block}
.ico.rem{border:1.2px solid var(--lc);border-radius:50%}
.ico.lin{border:1.2px solid var(--lc);border-radius:1px;transform:rotate(45deg) scale(.85)}
.iid,.id{font:400 11px var(--mono);color:var(--mute);flex:none}
.late{font:400 11px var(--mono);color:var(--bad);flex:none}
.rep{font:400 10px var(--mono);color:var(--mute);flex:none;letter-spacing:.06em}
/* bands */
.bands{display:flex;flex-direction:column;gap:10px}
.band{display:grid;grid-template-columns:250px minmax(0,1.25fr) minmax(0,1fr) 260px;background:var(--surface);border:1px solid var(--line);border-radius:16px;overflow:hidden;box-shadow:var(--rim),0 24px 48px -36px rgba(0,0,0,.9)}
.band>div{padding:18px 20px;min-width:0}
.band>div+div{border-left:1px solid var(--line)}
.idb{position:relative;background:linear-gradient(100deg,color-mix(in srgb,var(--lc) 9%,transparent),transparent 70%)}
.idb::before{content:"";position:absolute;left:0;top:18px;bottom:18px;width:2px;border-radius:2px;background:var(--lc)}
.band.quiet .idb{background:repeating-linear-gradient(135deg,transparent 0 7px,rgba(255,255,255,.03) 7px 8px)}
.band.quiet .idb::before{background:repeating-linear-gradient(180deg,var(--lc) 0 4px,transparent 4px 8px)}
.band.quiet .idb h2{color:color-mix(in srgb,var(--ink) 58%,transparent)}
.idb h2{font:600 21px/1.1 var(--sans);font-stretch:118%;letter-spacing:-.005em;margin:0 0 10px}
.idb .stw{display:inline-flex;align-items:center;gap:8px;font:400 10px var(--mono);letter-spacing:.14em;text-transform:uppercase}
.idb .stw::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 10px currentColor}
.band.active .stw{color:var(--ok)}.band.partial .stw{color:var(--warn)}.band.quiet .stw{color:var(--bad)}
.fresh{list-style:none;margin:20px 0 0;padding:0;display:flex;flex-direction:column;gap:11px}
.fresh li{display:grid;grid-template-columns:46px 1fr 38px;gap:10px;align-items:center;font:600 9px var(--sans);font-stretch:118%;letter-spacing:.14em;text-transform:uppercase;color:var(--mute)}
.fresh i{display:block;height:1px;background:var(--line);position:relative}
.fresh i::before{content:"";position:absolute;left:var(--zt);top:-3px;width:1px;height:7px;background:color-mix(in srgb,var(--bad) 55%,transparent)}
.fresh i b{position:absolute;left:0;top:-1px;height:3px;border-radius:2px;background:linear-gradient(90deg,transparent,var(--ok));transform-origin:left}
.fresh i b::after{content:"";position:absolute;right:0;top:-3px;width:2px;height:9px;border-radius:1px;background:var(--ok);box-shadow:0 0 8px var(--ok)}
.fresh i b.bad{background:linear-gradient(90deg,transparent,var(--bad))}
.fresh i b.bad::after{background:var(--bad);box-shadow:0 0 8px var(--bad)}
.fresh em{font:400 11px var(--mono);font-style:normal;text-align:right;letter-spacing:0;text-transform:none;color:var(--ink)}
.fresh em.bad{color:var(--bad)}
.band h3{font:600 9.5px var(--sans);font-stretch:125%;text-transform:uppercase;letter-spacing:.24em;color:var(--mute);margin:0 0 12px;display:flex;gap:8px;align-items:baseline}
.band h3 b{font:400 11px var(--mono);letter-spacing:0;color:var(--ink)}
.band h3+*{margin-bottom:18px}
.nx{list-style:none;margin:0;padding:0;counter-reset:n}
.nx li{counter-increment:n;display:grid;grid-template-columns:26px 1fr;gap:3px 8px;padding:9px 0;border-top:1px solid var(--line);font-size:13px;line-height:1.4}
.nx li:first-child{border-top:0;padding-top:0}
.nx li::before{content:counter(n,decimal-leading-zero);grid-row:1/3;font:400 11px/1.7 var(--mono);color:var(--accent)}
.nx .meta{font:400 10.5px var(--mono);color:var(--mute)}
.nx a{color:inherit;text-decoration:none}.nx a:hover{color:var(--accent)}
.nx .id{margin-right:6px}
.mini2{list-style:none;margin:0;padding:0}
.mini2 li{font-size:12.5px;padding:5px 0;display:flex;gap:10px;align-items:baseline}
.mini2 .age{font:400 11px var(--mono);flex:none;min-width:36px;color:var(--mute);text-align:right}
.mini2 .age.bad{color:var(--bad)}
.mini2 .t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mini2 a{color:inherit;text-decoration:none;display:contents}
.wk7 .cells{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.cell{border:1px solid var(--line);border-radius:8px;padding:6px 3px;min-height:62px;display:flex;flex-direction:column;align-items:center;gap:6px}
.cell.today{border-color:color-mix(in srgb,var(--accent) 70%,transparent);background:color-mix(in srgb,var(--accent) 6%,transparent)}
.cell>span{font:400 9.5px var(--mono);color:var(--mute);white-space:nowrap}
.cell.today>span{color:var(--accent)}
.dots{display:flex;flex-wrap:wrap;gap:3px;justify-content:center}
.dots i{display:block;flex:none;width:5px;height:5px;border-radius:50%;background:var(--lc)}
.dots i.rem{background:none;box-shadow:inset 0 0 0 1px var(--lc)}
.dots i.lin{border-radius:1px;transform:rotate(45deg)}
.dots em{font:400 9.5px var(--mono);color:var(--mute);font-style:normal}
.hrs{margin:12px 0 0;font:400 11px var(--mono);color:var(--mute)}
.hrs b{font-weight:400;color:var(--ink)}.hrs b.bad{color:var(--bad)}
/* panels */
.panel{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px 24px;box-shadow:var(--rim)}
.panel>h2{font:600 10px var(--sans);font-stretch:125%;letter-spacing:.26em;text-transform:uppercase;color:var(--mute);margin:0 0 18px}
.ag{gap:8px}
.ag-legend{font:400 11px var(--mono)}
.ag-col{background:transparent;border:1px solid var(--line);border-radius:12px;padding:10px}
.ag-col.today{background:color-mix(in srgb,var(--accent) 5%,transparent);box-shadow:none;border-color:color-mix(in srgb,var(--accent) 55%,transparent)}
.ag-col.over{background:color-mix(in srgb,var(--bad) 5%,transparent);border-color:color-mix(in srgb,var(--bad) 25%,transparent)}
.ag-h{font:600 9.5px var(--sans);font-stretch:125%;letter-spacing:.2em}
.ag-h b{font:300 20px var(--mono);letter-spacing:-.03em}
.ag-col.today .ag-h,.ag-col.today .ag-h b{color:var(--accent)}
.ag-i,.ag-col.today .ag-i{background:var(--soft);border-left:2px solid var(--lc);border-radius:6px;padding:6px 8px;font-size:12px}
.ag-t{font:400 10.5px var(--mono)}
.ag-rec{border-color:var(--line);font-family:var(--mono)}
.wk{border-top:1px solid var(--line)}
.wk>div{padding:9px 7px}
.wk-h{font:600 9.5px var(--sans);font-stretch:125%;letter-spacing:.2em}
.wk-h b{font:300 20px var(--mono);letter-spacing:-.03em}
.wk-name{font:600 12.5px var(--sans);font-stretch:112%}
.ev{background:var(--soft);border-left:2px solid var(--lc);border-radius:5px}
.plan b{font:300 18px var(--mono)}
.meter{height:2px;background:var(--line);overflow:visible}
.meter .ok{background:var(--ok);box-shadow:0 0 8px var(--ok)}
.meter .bad{background:var(--bad);box-shadow:0 0 8px var(--bad)}
.carried .its{list-style:none;margin:0;padding:0;columns:2 360px;column-gap:40px}
.carried .it{break-inside:avoid;display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--line);font-size:13px}
.carried .it .tt{flex:1}
.carried .lt{display:inline-flex;align-items:center;gap:6px;font:400 10px var(--mono);letter-spacing:.06em;color:var(--mute);flex:none}
.carried .lt::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--lc)}
details summary{font:400 11px var(--mono);color:var(--accent)}
.empty{color:var(--mute);font:400 11.5px var(--mono);margin:0}
@media (max-width:1180px){.band{grid-template-columns:220px minmax(0,1fr) minmax(0,1fr)}.wk7{grid-column:1/-1;border-left:0!important;border-top:1px solid var(--line)}}
@media (max-width:760px){.band{grid-template-columns:1fr}.band>div+div{border-left:0;border-top:1px solid var(--line)}.seg b{font-size:34px}.seg>*{padding-left:16px;margin-left:16px}}
@media (prefers-reduced-motion:no-preference){.fresh i b,.meter span{animation:sweep 1.1s cubic-bezier(.2,.8,.2,1) both}@keyframes sweep{from{transform:scaleX(0)}}.meter span{transform-origin:left}}
"""


# shared by B and D
def nx(i):
    if not i["na"]:
        return '<p class="empty">No open items</p>'
    lis = []
    for a in i["na"]:
        idh = f'<span class="id">{clean(a["id"])}</span>' if a["id"] else ""
        t = f'{idh}{clean(a["title"])}'
        if a["url"]:
            t = f'<a href="{esc(a["url"])}" target="_blank" rel="noopener">{t}</a>'
        lis.append(f'<li><span>{t}</span><span class="meta">{clean(a["src"])}{" · " + clean(a["meta"]) if a["meta"] else ""}</span></li>')
    return f'<ol class="nx">{"".join(lis)}</ol>'

def mini(items, datekey, late):
    if not items:
        return '<p class="empty">None</p>'
    lis = []
    for x in items[:3]:
        a = age(x[datekey]) or 0
        t = f'<span class="t">{clean(x["id"]) + " " if x.get("id") and x.get("kind") != "Reminder" else ""}{clean(x["title"])}</span>'
        if x.get("url"):
            t = f'<a href="{esc(x["url"])}" target="_blank" rel="noopener">{t}</a>'
        lis.append(f'<li><span class="age {"bad" if a > STALE or late else ""}">{a}d</span>{t}</li>')
    return f'<ul class="mini2">{"".join(lis)}</ul>'

def week7(i, link=False):
    """The lane's next 7 days as dot cells. With link, each cell opens Day by day filtered to this lane and that day."""
    cells = []
    for dd in DAYS:
        its = sorted((x for x in COLS[dd] if x["lane"] == i["key"]), key=lambda x: {"ev": 0, "rem": 1, "lin": 2}.get(x["kind"], 3))
        dots = "".join(f'<i class="{x["kind"]}"></i>' for x in its[:8]) + (f"<em>+{len(its) - 8}</em>" if len(its) > 8 else "")
        inner = f'<span>{dd.strftime("%a")[:2]} {dd.day}</span><div class="dots">{dots}</div>'
        cls = f'cell {"today" if dd == TODAY else ""}'
        if link:
            n = len(its)
            what = f'{n} item{"s" if n != 1 else ""}' if n else "nothing"
            label = f'{clean(i["short"])}, {dd.strftime("%A")} {dd.day}: {what}. Open in Day by day'
            cells.append(f'<a class="{cls}" href="#days?lane={i["key"]}&amp;day={dd.isoformat()}" aria-label="{label}" title="Open in Day by day">{inner}</a>')
        else:
            cells.append(f'<div class="{cls}">{inner}</div>')
    if i["budget"]:
        hrs = f'<b class="{"bad" if i["hours"] > i["budget"] else ""}">{i["hours"]:.1f}</b> of {i["budget"]} h booked'
    else:
        hrs = f'<b>{i["hours"]:.1f}</b> h booked, no budget'
    return f'<h3>Next 7 days</h3><div class="cells">{"".join(cells)}</div><p class="hrs">{hrs}</p>'



def build_b():
    def fresh(i):
        out = []
        for s, a in i["ages"].items():
            if a is None:
                out.append(f'<li><span>{s}</span><i style="--zt:{R.pos(STALE) / R.SPAN * 100:.0f}%"></i><em class="bad">never</em></li>')
                continue
            bad = "bad" if a > STALE else ""
            out.append(f'<li><span>{s}</span><i style="--zt:{R.pos(STALE) / R.SPAN * 100:.0f}%"><b class="{bad}" style="width:{max(R.pos(a) / R.SPAN * 100, 3):.0f}%"></b></i><em class="{bad}">{ago(a)}</em></li>')
        return "".join(out)

    bands = []
    for i in INFO:
        waiting = sorted(i["waiting"], key=lambda x: x.get("date") or "")
        over = sorted(i["overdue"], key=lambda x: x.get("due") or "")
        bands.append(f"""<section class="band l-{i['key']} {i['state']}" id="lane-{i['key']}">
<div class="idb"><h2>{clean(i['short'])}</h2><div class="stw">{clean(state_word(i))}</div><ul class="fresh">{fresh(i)}</ul></div>
<div><h3>Next</h3>{nx(i)}</div>
<div><h3>Waiting <b>{len(waiting)}</b></h3>{mini(waiting, "date", False)}<h3>Overdue <b>{len(over)}</b></h3>{mini(over, "due", True)}</div>
<div class="wk7">{week7(i)}</div></section>""")
    today = COLS[TODAY]
    over = COLS["over"]
    body = f"""<div class="wrap">
<header class="bar"><div class="mark">Work Cockpit<span>{TODAY.strftime("%a %d %b")} · w{WEEKNO} · {clean(GEN[11:])}</span></div>
<div class="seg"><a href="#carried">{TALLY[0]}</a><span>{TALLY[1]}</span><span>{TALLY[2]}</span></div></header>
<div class="ribbon"><span class="lbl">Today</span><ul>{"".join(item(x) for x in today) or '<li class="empty">Nothing dated today</li>'}</ul><a class="carry" href="#carried">{len(over)} carried over</a></div>
<div class="bands">{"".join(bands)}</div>
<section class="panel"><h2>Day by day</h2>{R.agenda()}</section>
<section class="panel carried" id="carried"><h2>Carried over · {len(over)}</h2>{listing(over, 12, late=True)}</section>
<section class="panel"><h2>Hours by lane</h2>{R.week()}</section>
</div>"""
    page("b", "Instrument", "family=Archivo:wdth,wght@100..125,300..700&family=DM+Mono:wght@300;400;500", B_CSS, body)


# =====================================================================
# C. Daybook
# =====================================================================
C_CSS = """
:root{--bg:#15231C;--panel:#F6F5F0;--ink:#1A221E;--mute:#6A716B;--line:#DCDAD0;--soft:#EDECE5;--accent:#7B2D27;
--gold:#CDAE6A;--foil:linear-gradient(175deg,#F1DFA8 0%,#C9A35A 45%,#E6CC8A 70%,#B48B45 100%);--parch:#E7E1CF;--parch2:#B9B39F;
--bad:#9C2F25;--badbg:#F2E2DD;--warn:#8C6216;--warnbg:#F0E7D2;--ok:#2E6A4A;--okbg:#E0EBE3;--zone:rgba(156,47,37,.06);
--axis:#3E5C8E;--bs:#6C717B;--delvion:#2D7A6E;--pbe:#8C4A70;--tfg:#9C6F22;--personal:#577B3F;
--sheet:0 1px 0 #fff inset,0 2px 0 #DDD9CD,0 30px 60px -34px rgba(0,0,0,.8);
--disp:"Cormorant Garamond",Garamond,serif;--sans:"Hanken Grotesk",system-ui,sans-serif;--mono:"Spline Sans Mono",ui-monospace,monospace;color-scheme:light}
body{background-color:var(--bg);background-image:radial-gradient(ellipse 120% 60% at 50% -10%,rgba(255,255,255,.07),transparent 60%),radial-gradient(rgba(0,0,0,.22) .8px,transparent 1px),radial-gradient(rgba(255,255,255,.035) .8px,transparent 1px);
background-size:auto,4px 4px,7px 7px;background-position:0 0,0 0,2px 3px;font-size:14px;-webkit-font-smoothing:antialiased}
.wrap{gap:30px;max-width:1380px}
.foil,.top2 h1,.stamp b,.top2 .sent b,.sec span{background:var(--foil);-webkit-background-clip:text;background-clip:text;color:transparent}
/* the cover */
.top2{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;padding:26px 4px 6px}
.top2 .ttl{display:flex;flex-direction:column;gap:16px}
.top2 h1{font:600 13px var(--disp);letter-spacing:.42em;text-transform:uppercase;margin:0}
.top2 .sent{font:italic 500 clamp(22px,2.6vw,32px)/1.25 var(--disp);color:var(--parch);margin:0;max-width:720px}
.top2 .sent b{font-style:normal;font-weight:600}
.top2 .sent b.bad{background:none;color:#E89C88}
.stamp{border:1px solid color-mix(in srgb,var(--gold) 70%,transparent);outline:1px solid color-mix(in srgb,var(--gold) 28%,transparent);outline-offset:4px;border-radius:2px;padding:14px 26px 12px;text-align:center;background:none;transform:none}
.stamp b{display:block;font:500 54px/1 var(--disp);letter-spacing:-.01em;margin:6px 0 8px}
.stamp span{display:block;font:500 9.5px var(--sans);letter-spacing:.3em;text-transform:uppercase;color:color-mix(in srgb,var(--gold) 80%,white)}
/* the open diary */
.spread{display:grid;grid-template-columns:1.05fr 1.35fr repeat(6,minmax(0,1fr));background:var(--panel);border:0;border-radius:6px 6px 8px 8px;position:relative;
box-shadow:0 1px 0 #fff inset,0 2px 0 #E3E0D6,0 4px 0 #D5D1C4,0 6px 0 #C9C4B5,0 40px 70px -30px rgba(0,0,0,.75)}
.spread::after{content:"";position:absolute;top:0;bottom:0;left:calc(100% * 2.4 / 8.4);width:30px;transform:translateX(-15px);background:linear-gradient(90deg,transparent,rgba(40,35,20,.09) 42%,rgba(40,35,20,.16) 50%,rgba(40,35,20,.09) 58%,transparent);pointer-events:none}
.pg{padding:18px 14px 24px;min-width:0;border-left:1px solid color-mix(in srgb,var(--line) 70%,transparent);
background:repeating-linear-gradient(180deg,transparent 0 27px,color-mix(in srgb,var(--line) 80%,transparent) 27px 28px) 0 64px/100% calc(100% - 64px) no-repeat}
.pg:first-child{border-left:0}
.pg h3{margin:0 0 18px;height:40px;display:flex;align-items:baseline;gap:8px;font:italic 500 17px var(--disp);letter-spacing:0;text-transform:none;color:var(--mute)}
.pg h3 b{font:500 32px/1 var(--disp);letter-spacing:-.01em;color:var(--ink)}
.pg h3 em{margin-left:auto;font:400 10px var(--mono);font-style:normal;color:var(--mute)}
.pg.today{background-color:#FCFBF7;position:relative}
.pg.today h3,.pg.today h3 b{color:var(--accent)}
.pg.today::before{content:"";position:absolute;top:-6px;right:16px;width:13px;height:80px;background:linear-gradient(90deg,#5E201C,#8E352E 45%,#6B2621);clip-path:polygon(0 0,100% 0,100% 100%,50% 86%,0 100%)}
.pg.today h3 em{margin-right:24px}
.pg.over h3,.pg.over h3 b{color:var(--bad)}
.pg .its{list-style:none;margin:0;padding:0}
.pg .it{line-height:28px;font-size:13px;display:block;overflow-wrap:anywhere}
.pg .it::before{content:"";display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--lc);margin-right:8px;vertical-align:2px}
.pg .k-rem::before,.pg .k-lin::before{display:none}
.pg .it .tt{background:none;padding:0}
.pg .it.past{opacity:.45}
.it>a{color:inherit;text-decoration:none}.it>a:hover .tt{color:var(--accent);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
.pg .w{font:400 10px var(--mono);color:var(--mute);margin-right:6px}
.pg .ico{display:inline-block;width:7px;height:7px;margin-right:7px}
.ico.rem{border:1.2px solid var(--lc);border-radius:50%}
.ico.lin{border:1.2px solid var(--lc);border-radius:1px;transform:rotate(45deg) scale(.85)}
.pg .iid{font:400 10px var(--mono);color:var(--accent);margin-right:5px}
.pg .lt{display:none}
.pg .late{font:italic 500 13.5px var(--disp);color:var(--bad);margin-left:6px}
.pg .rep{font:italic 500 13.5px var(--disp);color:var(--mute);margin-left:5px}
.pg details summary{font:italic 500 15px var(--disp);color:var(--accent);line-height:28px;padding:0}
.pg .empty{color:var(--mute);font:italic 500 15px/28px var(--disp);margin:0}
.legend{display:flex;flex-wrap:wrap;gap:8px 22px;font:500 9.5px var(--sans);letter-spacing:.22em;text-transform:uppercase;color:var(--parch2);margin:-6px 0 0}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{width:6px;height:6px;border-radius:50%;background:color-mix(in srgb,var(--lc) 55%,white);display:inline-block}
.sec{display:flex;align-items:baseline;gap:18px;flex-wrap:wrap;margin:12px 0 0}
.sec span{font:600 12px var(--disp);letter-spacing:.42em;text-transform:uppercase}
.sec em{font:italic 500 18px var(--disp);color:var(--parch2)}
/* lane cards: loose pages, each with its own ribbon */
.grid{gap:24px}
.card{position:relative;background:var(--panel);border:0;border-radius:6px;padding:24px 26px 22px;box-shadow:var(--sheet)}
.card::before{content:"";position:absolute;top:-4px;right:24px;width:10px;height:46px;background:var(--lc);clip-path:polygon(0 0,100% 0,100% 100%,50% 84%,0 100%)}
.card header{padding-right:30px}
.card header h2{font:italic 600 27px/1.05 var(--disp);letter-spacing:-.005em;color:var(--ink)}
.card header h2 .dot{display:none}
.pill{background:none!important;padding:0;border-radius:0;font:600 9.5px var(--sans);letter-spacing:.2em;text-transform:uppercase}
.srcages{font:400 10.5px var(--mono);color:var(--mute);margin:10px 0 0;line-height:1.7}
.srcages .bad{color:var(--bad)}
.stats{gap:0;margin:18px 0 4px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.st{background:none;border-radius:0;padding:12px 0 10px 14px;border-left:1px solid var(--line)}
.st:first-child{border-left:0;padding-left:0}
.st b{font:500 34px/1 var(--disp);margin-bottom:4px}
.st span{font:600 9px var(--sans);letter-spacing:.18em;text-transform:uppercase}
.card h3{font:600 9.5px var(--sans);letter-spacing:.22em;color:var(--mute);margin:20px 0 6px}
.h3n{font:italic 500 14px var(--disp);letter-spacing:0;text-transform:none}
.na li{padding:8px 0 8px 24px;border-top:1px solid var(--line)}
.na li::before{background:none;color:var(--accent);font:italic 600 19px/1 var(--disp);width:auto;height:auto;top:8px;text-align:left}
.ar{border-top:1px solid var(--line);padding:8px 0}
.mini{height:2px;background:var(--line)}
.id{color:var(--accent);font-size:10.5px}
.panel{background:var(--panel);border:0;border-radius:6px;padding:24px 26px;box-shadow:var(--sheet)}
.panel>h2{font:600 10px var(--sans);letter-spacing:.24em;color:var(--mute)}
.panel>h2 em{font:italic 500 16px var(--disp);letter-spacing:0;text-transform:none}
.wk-h b{font:500 24px var(--disp)}
.wk-h.today b{color:var(--accent)}
.wk-name{font:italic 600 17px var(--disp)}
.ev{background:var(--soft);border-left:2px solid var(--lc);border-radius:2px}
.plan b{font:500 21px var(--disp)}
.meter{height:2px;background:var(--line)}
details summary{color:var(--accent)}
@media (max-width:1100px){.spread{grid-template-columns:repeat(8,minmax(180px,1fr));overflow-x:auto;scroll-snap-type:x mandatory}.pg{scroll-snap-align:start}.spread::after{display:none}.pg.today::before{top:0}}
@media (max-width:600px){.stamp{padding:10px 18px}.stamp b{font-size:40px}.card{padding:22px 18px}.panel{padding:20px 16px}}
"""


def build_c():
    over = COLS["over"]
    pages = [f'<div class="pg over"><h3>Carried<em>{len(over)}</em></h3>{listing(over, 9, late=True)}</div>']
    for dd in DAYS:
        n = len(COLS[dd])
        label = dd.strftime("%a")
        first = 14 if dd == TODAY else 9
        pages.append(f'<div class="pg {"today" if dd == TODAY else ""}"><h3>{label}<b>{dd.day}</b><em>{n or ""}</em></h3>{listing(COLS[dd], first)}</div>')
    legend = "".join(f'<span class="l-{i["key"]}"><i></i>{clean(i["short"])}</span>' for i in INFO)
    byk = {x["key"]: x for x in INFO}
    order = sorted(LANE_CFG, key=lambda lc: (-len(byk[lc["key"]]["stale_src"]), -max([a for a in byk[lc["key"]]["ages"].values() if a is not None] or [10**4])))
    t = TALLY
    body = f"""<div class="wrap">
<header class="top2"><div class="ttl"><h1>Work Cockpit</h1>
<p class="sent">{t[0]}, {t[1]}, and {t[2]}.</p></div>
<div class="stamp"><span>{TODAY.strftime("%A")}</span><b>{TODAY.day} {TODAY.strftime("%b")}</b><span>week {WEEKNO} · {clean(GEN[11:])}</span></div></header>
<div class="spread" id="carried">{"".join(pages)}</div>
<div class="legend">{legend}<span>○ reminder</span><span>◇ Linear due</span></div>
<p class="sec"><span>Lanes</span><em>most neglected first: the lane you are avoiding is the first one you see</em></p>
<div class="grid">{cards(order)}</div>
<section class="panel"><h2>Hours by lane<em>next 7 days of calendar, booked against budget</em></h2>{R.week()}</section>
</div>"""
    page("c", "Agenda", "family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500;1,600&family=Hanken+Grotesk:wght@400;500;600&family=Spline+Sans+Mono:wght@400;500", C_CSS, body)


# =====================================================================
# D. Precision (the Apple / Mercedes reading)
# =====================================================================
D_CSS = """
:root{--bg:#F5F5F7;--panel:#FFFFFF;--ink:#1D1D1F;--mute:#6E6E73;--faint:#AEAEB2;--line:#E5E5EA;--soft:#F2F2F7;--accent:#0066CC;
--bad:#D70015;--red:#FF3B30;--badbg:#FFF1F0;--warn:#C93400;--warnbg:#FFF4E5;--ok:#248A3D;--okbg:#EAF7EE;--zone:rgba(255,59,48,.06);
--axis:#0A84FF;--bs:#8E8E93;--delvion:#30B0C7;--pbe:#AF52DE;--tfg:#FF9500;--personal:#34C759;
--glass:rgba(245,245,247,.72);--tacc:#2997FF;--sh:0 1px 2px rgba(0,0,0,.04),0 8px 28px -12px rgba(0,0,0,.10);
--disp:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue",system-ui,sans-serif;
--sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",system-ui,sans-serif;
--mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#000;--panel:#1C1C1E;--ink:#F5F5F7;--mute:#98989D;--faint:#636366;--line:#2C2C2E;--soft:#2C2C2E;--accent:#2997FF;
--bad:#FF453A;--red:#FF453A;--badbg:#2A1513;--warn:#FF9F0A;--warnbg:#2B1E0B;--ok:#30D158;--okbg:#0F2716;--zone:rgba(255,69,58,.08);
--axis:#409CFF;--bs:#98989D;--delvion:#40C8E0;--pbe:#BF5AF2;--tfg:#FFB340;--personal:#30D158;
--glass:rgba(22,22,23,.72);--tacc:#0066CC;--sh:0 0 0 1px rgba(255,255,255,.06) inset;color-scheme:dark}}
body{font:15px/1.47 var(--sans);letter-spacing:-.01em;-webkit-font-smoothing:antialiased;padding-top:0}
.wrap{max-width:1240px;gap:0}
a:hover .t,.it>a:hover .tt,.nx a:hover{color:var(--accent);text-decoration:none}
/* local nav: frosted, like apple.com product pages */
.lnav{position:sticky;top:0;z-index:8;margin:0 calc(-1 * max(16px,env(safe-area-inset-left,0px)));padding:0 max(16px,env(safe-area-inset-left,0px));
background:var(--glass);backdrop-filter:saturate(180%) blur(20px);-webkit-backdrop-filter:saturate(180%) blur(20px);border-bottom:1px solid color-mix(in srgb,var(--ink) 9%,transparent)}
.lnav>div{max-width:1240px;margin:0 auto;height:52px;display:flex;align-items:center;gap:28px}
.lnav b{font:600 19px var(--disp);letter-spacing:-.02em;margin-right:auto}
.lnav a{font-size:12.5px;color:var(--mute);letter-spacing:0}
.lnav a:hover{color:var(--ink)}
.lnav a.home{display:inline;font:inherit;color:inherit;letter-spacing:inherit}
.lnav span{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;padding-left:20px;border-left:1px solid var(--line)}
.lnav a.gear{display:grid;place-items:center;width:30px;height:30px;margin:0 -6px 0 -14px;border-radius:8px;color:var(--mute)}
.lnav a.gear:hover{color:var(--ink);background:color-mix(in srgb,var(--ink) 7%,transparent)}
.lnav a.gear svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.6}
section[id],div[id]{scroll-margin-top:72px}
/* title */
.hero{padding:56px 0 28px}
.hero p{font:600 17px var(--disp);color:var(--mute);margin:0 0 6px;letter-spacing:-.01em}
.hero h1{font:700 clamp(40px,5.6vw,64px)/1.05 var(--disp);letter-spacing:-.028em;margin:0}
/* readouts */
.kpi{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));background:var(--panel);border-radius:22px;box-shadow:var(--sh);margin-bottom:56px}
.kpi:has(+.duo){margin-bottom:20px}
.kpi>*{padding:26px 30px 24px;display:flex;flex-direction:column;gap:4px;color:inherit}
.kpi>*+*{border-left:1px solid var(--line)}
.kpi b{font:600 54px/1 var(--disp);letter-spacing:-.035em;font-variant-numeric:tabular-nums}
.kpi b small{font-size:22px;font-weight:500;color:var(--mute);letter-spacing:-.01em;margin-left:4px}
.kpi .red b{color:var(--bad)}
.kpi strong{font:600 15px var(--sans);margin-top:10px}
.kpi span{font-size:13px;color:var(--mute);line-height:1.4}
.kpi{overflow:hidden}
.kpi>a,.kpi a.cover{text-decoration:none;cursor:pointer}
.kpi>a:hover strong,.kpi .st:has(a.cover:hover) strong{color:var(--accent)}
.kpi strong{transition:color .15s}
.kpi .st{position:relative}
.kpi a.cover{color:inherit}
.kpi a.cover::after{content:"";position:absolute;inset:0}
.kpi .st span a{position:relative;z-index:1;color:inherit;text-decoration:underline;text-decoration-color:var(--line);text-underline-offset:3px;transition:color .15s}
.kpi .st span a:hover{color:var(--accent);text-decoration-color:currentColor}
.kpi>a:focus-visible,.kpi a.cover:focus-visible{outline:none}
.kpi>a:focus-visible,.kpi .st:has(a.cover:focus-visible){box-shadow:inset 0 0 0 2px var(--accent)}
.kpi .st span a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px}
/* a lane opened from a summary tile rings once in its own colour */
.lane:target{animation:ring 1.8s cubic-bezier(.25,.1,.25,1)}
@keyframes ring{0%,45%{box-shadow:0 0 0 2px var(--lc),var(--sh)}100%{box-shadow:var(--sh)}}
@media (prefers-reduced-motion:reduce){.lane:target{animation:none;box-shadow:0 0 0 2px var(--lc),var(--sh)}}
/* tiles */
.tile{background:var(--panel);border-radius:22px;box-shadow:var(--sh);padding:26px 28px;min-width:0}
.th{display:flex;align-items:baseline;gap:10px;margin:0 0 18px}
.th h2{font:600 22px/1.2 var(--disp);letter-spacing:-.02em;margin:0}
.th span{font-size:13px;color:var(--mute);font-variant-numeric:tabular-nums}
.th .r{margin-left:auto}
.duo{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:20px;margin-bottom:56px}
.sec{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:0 0 18px}
.sec h2{font:700 32px/1.1 var(--disp);letter-spacing:-.025em;margin:0}
.sec p{margin:0;font-size:14px;color:var(--mute)}
.block{margin-bottom:56px}
/* item atoms */
.its,.tl{list-style:none;margin:0;padding:0}
.it>a{display:contents}
.it .w{font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums;flex:none}
.it .ico{flex:none;width:12px;height:12px;display:inline-block}
.ico.rem{border:1.5px solid var(--lc);border-radius:50%}
.ico.lin{border:1.5px solid var(--lc);border-radius:2px;transform:rotate(45deg) scale(.72)}
.it .iid,.id{font:500 11.5px var(--mono);color:var(--mute);flex:none;letter-spacing:0}
.it .tt{flex:1;min-width:0;overflow-wrap:anywhere}
.it .lt{flex:none;display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--mute)}
.it .lt::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--lc)}
.it .late{flex:none;font-size:12.5px;font-weight:500;color:var(--bad);font-variant-numeric:tabular-nums}
.it .rep{flex:none;font-size:11.5px;color:var(--mute)}
/* today, Calendar day view */
.tl{display:flex;flex-direction:column;gap:6px}
.tl .it{display:flex;align-items:center;gap:12px;padding:10px 14px 10px 12px;border-radius:10px;background:color-mix(in srgb,var(--lc) 10%,var(--panel));box-shadow:inset 3px 0 0 var(--lc);font-size:14.5px;line-height:1.35}
.tl .it .w{min-width:44px}
.tl .k-rem .w{min-width:0}
.tl .it.past{opacity:.42}
.tl .anytime{font-size:12px;font-weight:600;color:var(--mute);padding:0 2px 2px;text-transform:uppercase;letter-spacing:.04em}
.now{display:flex;align-items:center;gap:8px;margin:4px 0;color:var(--red);font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
.now::after{content:"";flex:1;height:1.5px;background:var(--red);border-radius:1px}
.now i{width:9px;height:9px;border-radius:50%;background:var(--red);order:1;margin-left:-4px}
.now::after{order:2}
/* carried over, Reminders list */
.its .it{display:flex;align-items:baseline;gap:12px;padding:11px 0;border-top:1px solid var(--line);font-size:14px}
.its .it:first-child{border-top:0;padding-top:2px}
.its .it .ico{align-self:center}
details summary{list-style:none;cursor:pointer;color:var(--accent);font-size:13.5px;padding:12px 0 0}
details summary::-webkit-details-marker{display:none}
details summary::after{content:" \\203A"}
details[open] summary::after{content:""}
.empty{color:var(--mute);font-size:14px;margin:0}
/* lanes: instrument rows */
.lanes{display:flex;flex-direction:column;gap:14px}
.lane{display:grid;grid-template-columns:316px minmax(0,1.25fr) minmax(0,1fr) 256px;background:var(--panel);border-radius:22px;box-shadow:var(--sh);overflow:hidden}
.lane>div{padding:24px 24px 22px;min-width:0}
.lane>div+div{border-left:1px solid var(--line)}
.who h3{display:flex;align-items:center;gap:10px;font:600 22px/1.15 var(--disp);letter-spacing:-.02em;margin:0;text-transform:none;color:var(--ink)}
.who h3::before{content:"";width:10px;height:10px;border-radius:50%;background:var(--lc);flex:none}
.lane.quiet .who h3::before{background:none;box-shadow:inset 0 0 0 2px var(--lc)}
.stw{margin:6px 0 0 20px;font-size:13px;font-weight:500}
.lane.active .stw{color:var(--ok)}.lane.partial .stw{color:var(--warn)}.lane.quiet .stw{color:var(--bad)}
/* the gauge: thin track, day ticks, red zone from the stale mark, one needle */
.gg{list-style:none;margin:22px 0 0;padding:0;display:flex;flex-direction:column;gap:12px}
.gg li{display:grid;grid-template-columns:52px minmax(0,1fr) 46px;gap:12px;align-items:center;font-size:12px;color:var(--mute)}
.gg em{font-style:normal;text-align:right;color:var(--ink);font-variant-numeric:tabular-nums;font-weight:500}
.gg em.bad{color:var(--bad)}
.g{position:relative;height:16px}
.g::before{content:"";position:absolute;left:0;right:0;top:11px;height:1px;background:var(--line)}
.g::after{content:"";position:absolute;left:var(--z);right:0;top:10px;height:3px;border-radius:2px;background:color-mix(in srgb,var(--red) 22%,transparent)}
.g .tk{position:absolute;top:7px;width:1px;height:4px;background:var(--faint)}
.g .tk.z{top:4px;height:8px;background:var(--red)}
.g .fl{position:absolute;left:0;top:10px;height:3px;border-radius:2px;background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--lc) 70%,transparent));transform-origin:left;z-index:1}
.g .nd{position:absolute;top:1px;width:2px;height:15px;border-radius:1px;background:var(--ink);transform:translateX(-1px);z-index:2;box-shadow:0 0 0 2px var(--panel)}
.g .nd.bad{background:var(--red)}
.gg .sc{margin-top:-4px;font-size:10px;color:var(--faint)}.gg .sc i{position:relative;height:12px;display:block;font-style:normal}
.gg .sc b{position:absolute;transform:translateX(-50%);font-weight:500;font-variant-numeric:tabular-nums}.gg .sc b:first-child{transform:none}.gg .sc b:last-child{transform:translateX(-100%)}
.lane h4{font:600 12px var(--sans);text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin:0 0 12px;display:flex;gap:6px}
.lane h4 b{font-weight:600;color:var(--ink)}
.lane h4+*{margin-bottom:22px}
.lane>div>:last-child{margin-bottom:0}
.nx{list-style:none;margin:0;padding:0;counter-reset:n}
.nx li{counter-increment:n;display:grid;grid-template-columns:22px 1fr;gap:2px 8px;padding:10px 0;border-top:1px solid var(--line);font-size:14px;line-height:1.38}
.nx li:first-child{border-top:0;padding-top:0}
.nx li::before{content:counter(n);grid-row:1/3;width:20px;height:20px;border-radius:50%;background:var(--soft);color:var(--mute);font:600 11px/20px var(--sans);text-align:center;margin-top:-1px}
.nx .meta{font-size:12px;color:var(--mute)}
.nx .id{margin-right:6px}
.mini2{list-style:none;margin:0;padding:0}
.mini2 li{display:flex;gap:10px;align-items:baseline;padding:5px 0;font-size:13.5px}
.mini2 .age{flex:none;min-width:34px;text-align:right;font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums;font-weight:500}
.mini2 .age.bad{color:var(--bad)}
.mini2 .t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mini2 a{display:contents}
.wk7 .cells{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.cell{display:flex;flex-direction:column;align-items:center;gap:8px;padding:6px 0 10px;border-radius:12px;background:var(--soft);min-height:76px}
.cell>span{font-size:13px;font-weight:600;color:var(--ink)!important;color:var(--mute);white-space:nowrap;font-variant-numeric:tabular-nums;display:flex;flex-direction:column;align-items:center;gap:2px;line-height:1.2}
.cell>span small{font-size:9.5px;font-weight:500;color:var(--mute);letter-spacing:.02em}
.cell.today>span{color:#fff!important;background:var(--red);border-radius:999px;width:24px;height:36px;justify-content:center}.cell.today>span small{color:rgba(255,255,255,.85)}
/* Same shapes as Day by day: solid bar = booked time (event), ring = reminder, outlined diamond = Linear due. */
/* Bars take a full row each; rings and diamonds sit side by side underneath, up to four per row. */
.dots{display:flex;flex-wrap:wrap;gap:5px 3px;justify-content:center;align-items:center;box-sizing:border-box;width:100%;max-width:34px;padding:0}
.dots i{display:block;flex:none;box-sizing:border-box;width:6px;height:6px;padding:0;border-radius:50%;background:none;border:1.25px solid var(--lc)}
.dots i.ev{flex:0 0 100%;height:4px;border:0;border-radius:2px;background:var(--lc)}
.dots i.lin{width:5px;height:5px;margin:0 .5px;border-radius:1px;transform:rotate(45deg)}
.dots em{font-size:10px;font-style:normal;color:var(--mute)}
.hrs{margin:14px 0 0;font-size:12.5px;color:var(--mute)}
.hrs b{font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}.hrs b.bad{color:var(--bad)}
/* reused components under Apple materials */
.ag{gap:8px}
.ag-legend{font-size:12.5px;margin:0 0 14px}
.ag-col{background:var(--soft);border-radius:14px;padding:12px 10px}
.ag-col.today{background:var(--panel);box-shadow:inset 0 0 0 1px var(--line),0 6px 18px -10px rgba(0,0,0,.18)}
.ag-col.over{background:var(--badbg)}
.ag-h{font-size:11px;font-weight:600;letter-spacing:.04em;align-items:center}
.ag-h b{font:600 17px var(--disp);letter-spacing:-.01em}
.ag-col.today .ag-h{color:var(--red)}
.ag-col.today .ag-h b{color:#fff;background:var(--red);border-radius:999px;min-width:28px;height:28px;display:inline-grid;place-items:center;padding:0 6px}
.ag-i,.ag-col.today .ag-i{background:color-mix(in srgb,var(--lc) 10%,var(--panel));border-left:0;box-shadow:inset 3px 0 0 var(--lc);border-radius:7px;padding:6px 8px 6px 10px;font-size:12.5px}
.ag-col.over .ag-i{background:var(--panel)}
/* lane filter on Day by day, and the day cells that open it */
#days .sec{align-items:center}
.lf{display:flex;flex-wrap:wrap;gap:6px;margin-left:auto}
.lf button{font:500 12.5px/1 var(--sans);color:var(--ink);background:var(--panel);border:0;border-radius:999px;padding:7px 12px;display:inline-flex;align-items:center;gap:7px;cursor:pointer;box-shadow:inset 0 0 0 1px var(--line);transition:background .15s,color .15s,box-shadow .15s}
.lf button i{width:7px;height:7px;border-radius:50%;background:var(--lc)}
.lf button:hover{background:var(--soft)}
.lf button[aria-pressed="true"]{background:var(--ink);color:var(--panel);box-shadow:none}
.lf button:focus-visible,a.cell:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
a.cell{text-decoration:none;color:inherit;cursor:pointer;transition:background .15s,transform .15s}
a.cell:hover{background:color-mix(in srgb,var(--lc) 16%,var(--soft))}
a.cell:active{transform:scale(.96)}
.ag-i[hidden],.ag-i[data-gone],.ag-n[hidden],.ag-col ul[hidden],.ag-col details[hidden]{display:none!important}
.ag-col details[data-lf]>summary{display:none}
.ag-col{transition:box-shadow .25s;scroll-margin-top:72px}
.ag-col.pick{box-shadow:inset 0 0 0 2px var(--pick)}
.ag-col.today.pick{box-shadow:inset 0 0 0 2px var(--pick),0 6px 18px -10px rgba(0,0,0,.18)}
@media (max-width:760px){.lf{margin-left:0}}
.ag-t{font:500 11px var(--sans);font-variant-numeric:tabular-nums}
.ag-rec{border:0;background:var(--soft);border-radius:4px;padding:1px 5px;font-size:10.5px}
.wk{border-top:0}
.wk>div{padding:10px 8px;border-bottom-color:var(--line)}
.wk-h{font-size:11px;font-weight:600;letter-spacing:.04em}
.wk-h b{font:600 18px var(--disp);letter-spacing:-.01em;margin-top:2px}
.wk-h.today,.wk-h.today b{color:var(--red)}
.wk-name{font:600 14px var(--disp);letter-spacing:-.01em}
.ev{background:color-mix(in srgb,var(--lc) 10%,var(--panel));border-left:0;box-shadow:inset 3px 0 0 var(--lc);border-radius:6px;padding:4px 8px}
.plan b{font:600 17px var(--disp)}
.meter{height:4px;border-radius:2px;background:var(--soft)}
.foot{margin:8px 0 0;font-size:12px;color:var(--mute);text-align:center}
/* test sources */
.chip{font:600 10px/1 var(--sans);letter-spacing:.07em;text-transform:uppercase;color:var(--mute);border:1px solid var(--line);border-radius:999px;padding:4px 8px;align-self:center}
.prt{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0 40px}
.prt.one{grid-template-columns:minmax(0,1fr)}
.prt h4{font:600 12px var(--sans);text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin:0 0 6px;display:flex;gap:6px}
.prt h4 b{color:var(--ink)}
.prs .it{align-items:center}
.prs .ico.pr{width:8px;height:8px;border-radius:50%;background:var(--lc,var(--faint))}
.prs .tt small{display:block;font:500 11.5px var(--mono);color:var(--mute);letter-spacing:0;margin-top:2px}
.prs .w{min-width:46px;text-align:right}
.prs .late{min-width:74px;text-align:right}
.prs .late.ok{color:var(--mute);font-weight:400}
.qline{margin:14px 0 0;font-size:12.5px;color:var(--mute)}
/* tracked time: one row per lane on one scale; bar = this week, tick = last week, ring = budget */
.rzl{list-style:none;margin:0;padding:0}
.rzl li{display:grid;grid-template-columns:150px minmax(0,1fr) 64px 80px;align-items:center;gap:0 20px;padding:10px 0;border-top:1px solid var(--line)}
.rzl li.hd{border-top:0;padding:0 0 8px}
.rzl li.hd b,.rzl li.hd em{font:600 11px var(--sans);text-transform:uppercase;letter-spacing:.05em;color:var(--mute)}
.rzl .nm{font:600 14px var(--disp);letter-spacing:-.01em;display:flex;align-items:center;gap:8px;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rzl li:not(.hd) .nm::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--lc);flex:none}
.rzl li.x{--lc:var(--faint)}
.rzl li.x .nm{font-weight:500;color:var(--mute)}
.rzl .tr{position:relative;height:6px;border-radius:3px;background:var(--soft)}
.rzl .fl{position:absolute;top:0;bottom:0;left:0;border-radius:3px;background:var(--lc)}
.rzl .fl.over{background:var(--bad)}
.rzl .pv{position:absolute;top:-5px;bottom:-5px;width:2px;margin-left:-1px;border-radius:1px;background:var(--ink);opacity:.5}
.rzl .bg{position:absolute;top:50%;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;box-shadow:inset 0 0 0 1.5px var(--mute);background:var(--panel)}
.rzl b,.rzl em{text-align:right;font-variant-numeric:tabular-nums}
.rzl li b{font:600 17px var(--disp);letter-spacing:-.01em}
.rzl li em{font-style:normal;font-size:14px;color:var(--mute)}
.rzl li.zero .nm,.rzl li.zero b{color:var(--faint)}
@media (prefers-reduced-motion:no-preference){.rzl .fl{transform-origin:left;animation:rzg .9s cubic-bezier(.2,.8,.2,1) both}@keyframes rzg{from{transform:scaleX(0)}}}
@media (max-width:760px){.rzl li{grid-template-columns:92px minmax(0,1fr) 40px 44px;gap:0 12px}.rzl li.hd b,.rzl li.hd em{font-size:9.5px;letter-spacing:.02em}}
@media (max-width:760px){.prt{grid-template-columns:1fr;gap:22px}.prs .it{flex-wrap:nowrap}.prs .it .w{display:none}}
/* reminder actions: Done ring, menu, Undo toast, duplicates */
.ag-i[data-rid]{cursor:pointer;transition:background .15s,box-shadow .15s,opacity .24s ease .14s}
.ag-i[data-rid]:hover,.ag-i[data-rid][aria-expanded="true"]{background:color-mix(in srgb,var(--lc) 18%,var(--panel))}
.ag-col.over .ag-i[data-rid]:hover,.ag-col.over .ag-i[data-rid][aria-expanded="true"]{background:color-mix(in srgb,var(--lc) 8%,var(--panel))}
.ag-i[data-rid]:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ag-i .ck{appearance:none;-webkit-appearance:none;border:0;background:none;padding:0;cursor:pointer;color:var(--lc);border-radius:50%;display:inline-grid;place-items:center;width:20px;height:20px;margin:-5px 0 -5px -5px;vertical-align:-5px}
.ag-i .ck svg{width:10px;height:10px;display:block;overflow:visible;fill:none;stroke:var(--lc);stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.ag-i .ck circle{transition:fill .18s}
.ag-i .ck path{opacity:0;transition:opacity .15s}
.ag-i .ck:hover circle,.ag-i .ck:focus-visible circle{fill:color-mix(in srgb,var(--lc) 14%,transparent)}
.ag-i .ck:hover path,.ag-i .ck:focus-visible path{opacity:1}
.ag-i.leaving .ck circle{fill:var(--lc)}
.ag-i.leaving .ck path{opacity:1;stroke:#fff}
.ag-i .ck:focus-visible{outline:2px solid var(--accent);outline-offset:0}
.ag-i.leaving,.ag-i.moving{opacity:0}
.ag-i .rn{font:inherit;width:100%;border:0;border-radius:4px;padding:1px 4px;background:var(--panel);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line)}
.it[hidden],.dp[hidden],.block[hidden]{display:none!important}
.it .ck{flex:none;appearance:none;-webkit-appearance:none;border:0;background:none;padding:0;margin:-6px;width:24px;height:24px;display:grid;place-items:center;cursor:pointer;color:var(--lc);border-radius:50%}
/* pinned to the first line of the title, centred on its lowercase letters, so a wrapped title keeps the ring beside line one */
.its .it .ck{align-self:start;font:inherit;margin:calc(.5lh - 12px) -6px -6px;margin-top:round(calc(.5lh - 12px),1px)}
.it .ck svg{display:block;overflow:visible;fill:none;stroke:var(--lc);stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.it .ck circle{transition:fill .18s}
.it .ck path{opacity:0;transition:opacity .15s}
.it .ck:hover circle,.it .ck:focus-visible circle{fill:color-mix(in srgb,var(--lc) 14%,transparent)}
.it .ck:hover path,.it .ck:focus-visible path{opacity:1}
.it.leaving .ck circle{fill:var(--lc)}
.it.leaving .ck path{opacity:1;stroke:#fff}
.it.leaving,.it.moving,.dp.leaving{opacity:0;transition:opacity .24s ease .14s}
.it .mo{flex:none;appearance:none;-webkit-appearance:none;border:0;background:none;padding:0;width:28px;height:24px;margin:-4px -6px -4px 0;display:grid;place-items:center;border-radius:7px;color:var(--mute);cursor:pointer;opacity:0;transition:opacity .15s,background .15s,color .15s}
.its .it .mo{align-self:start;font:inherit;margin:calc(.5lh - 12px) -6px -4px 0}
.it .mo svg{fill:currentColor}\n.it .tail{display:contents}\n@media (max-width:600px){.its .it.act{display:grid;grid-template-columns:auto auto minmax(0,1fr) auto;column-gap:12px;row-gap:3px;align-items:baseline}.its .it.act .ck{grid-area:1/1}.its .it.act .w{grid-area:1/2}.its .it.act .tt{grid-row:1;grid-column:2/4}.its .it.act .w+.tt{grid-column:3}.its .it.act .tail{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;grid-row:2;grid-column:2/4}.its .it.act .w~.tail{grid-column:3}.its .it.act .mo{grid-area:1/4}}
.it.act:hover .mo,.it.act:focus-within .mo,.it .mo[aria-expanded=true]{opacity:1}
.it .mo:hover,.it .mo[aria-expanded=true]{background:color-mix(in srgb,var(--ink) 8%,transparent);color:var(--ink)}
@media (hover:none){.it .mo{opacity:1}}
.it .rn{font:inherit;color:inherit;letter-spacing:inherit;width:100%;box-sizing:border-box;background:var(--panel);border:0;border-radius:6px;padding:2px 6px;margin:-3px -7px;outline:0;box-shadow:0 0 0 1px color-mix(in srgb,var(--accent) 60%,transparent),0 0 0 4px color-mix(in srgb,var(--accent) 18%,transparent)}
.menu{position:fixed;z-index:20;min-width:224px;padding:6px;border-radius:12px;background:color-mix(in srgb,var(--panel) 86%,transparent);backdrop-filter:saturate(180%) blur(24px);-webkit-backdrop-filter:saturate(180%) blur(24px);box-shadow:0 0 0 .5px color-mix(in srgb,var(--ink) 18%,transparent),0 14px 40px -10px rgba(0,0,0,.3);font-size:13.5px;letter-spacing:-.005em}
.menu[hidden]{display:none}
.menu button{appearance:none;-webkit-appearance:none;border:0;background:none;font:inherit;color:var(--ink);width:100%;display:flex;justify-content:space-between;align-items:baseline;gap:20px;padding:6px 10px;border-radius:6px;text-align:left;cursor:pointer}
.menu button small{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums}
.menu button[role=menuitem]:focus{background:var(--accent);color:#fff;outline:0}
.menu button[role=menuitem]:focus small{color:rgba(255,255,255,.78)}
.menu button:disabled{color:var(--faint);cursor:default}
.menu .bad{color:var(--bad)}
.menu hr{border:0;height:1px;background:color-mix(in srgb,var(--ink) 10%,transparent);margin:5px 10px}
.menu .pick{display:flex;gap:6px;align-items:center;padding:2px 2px 6px 8px}
.menu .pick[hidden]{display:none}
.menu .pick input{flex:1;min-width:0;font:inherit;color:var(--ink);background:color-mix(in srgb,var(--ink) 6%,transparent);border:0;border-radius:6px;padding:5px 8px}
.menu .pick button{width:auto;flex:none;justify-content:center;background:var(--accent);color:#fff;padding:5px 12px}
.toast{position:fixed;left:50%;bottom:max(24px,env(safe-area-inset-bottom));z-index:30;transform:translate(-50%,16px);opacity:0;pointer-events:none;display:flex;align-items:center;gap:18px;padding:11px 12px 11px 18px;border-radius:14px;background:color-mix(in srgb,var(--ink) 88%,transparent);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);color:var(--bg);font-size:14px;box-shadow:0 14px 34px -12px rgba(0,0,0,.4);overflow:hidden;width:max-content;max-width:calc(100vw - 32px);transition:opacity .2s,transform .3s cubic-bezier(.2,.8,.2,1)}
.toast:not(.undo){padding-right:18px}
.toast.on{opacity:1;transform:translate(-50%,0);pointer-events:auto}
.toast button{display:none;appearance:none;-webkit-appearance:none;border:0;background:none;font:600 14px var(--sans);color:var(--tacc);padding:4px 6px;border-radius:6px;cursor:pointer}
.toast.undo button{display:block}
.toast i{position:absolute;left:0;bottom:0;height:2px;width:100%;background:var(--tacc);transform-origin:left;transform:scaleX(0)}
.toast.run i{animation:drain 5s linear both}
@keyframes drain{from{transform:scaleX(1)}to{transform:scaleX(0)}}
@media (prefers-reduced-motion:reduce){.toast{transition:opacity .2s}.toast i{display:none}}
.dupb{margin-bottom:40px}
.dupb .sec{margin-bottom:10px;gap:12px}
.dupb .sec h2{font:600 17px/1.3 var(--sans);letter-spacing:-.01em}
.dupb .sec p{font-size:13px}
.dups ul{list-style:none;margin:0;padding:0}
.dp{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--line)}
.dp:first-child{border-top:0}
.dq{display:flex;flex-direction:column;align-items:flex-start;gap:3px;padding:9px 18px 10px 0;min-width:0}
.dq+.dq{border-left:1px solid var(--line);padding-left:18px}
.dq .tt{font-size:13.5px;overflow-wrap:anywhere}
.dq .meta{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px;font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums}
.dq .ln{display:inline-flex;align-items:center;gap:6px}
.dq .ln::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--lc)}
.dq .meta .bad{color:var(--bad)}
.dq .keep{appearance:none;-webkit-appearance:none;border:0;background:none;color:var(--accent);font:500 12px var(--sans);padding:0;cursor:pointer}
.dq .keep:hover,.dq .keep:focus-visible{text-decoration:underline;text-underline-offset:3px}
.dups details summary{padding:8px 0 0;font-size:12.5px}
.dups details[open] summary{padding-bottom:4px}
.dups details .dp:first-child{border-top:1px solid var(--line)}
@media (max-width:760px){.dp{grid-template-columns:1fr}.dq+.dq{border-left:0;padding-left:0;padding-top:2px}.dq:first-child{padding-bottom:4px}.it .mo{order:6}}
.cg h3{display:flex;align-items:baseline;gap:8px;margin:0 0 6px;font:600 11.5px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--mute)}
.cg h3 small{font-size:12px;font-weight:400;letter-spacing:0;text-transform:none;color:var(--faint)}
.cg h3 b{margin-left:auto;font-weight:600;letter-spacing:0;color:var(--ink);font-variant-numeric:tabular-nums}
.cg[data-g=stale] h3{color:var(--bad)}
.cg+.cg{margin-top:24px}
.cg[hidden],.cge[hidden],.trb[hidden]{display:none!important}
.trb{appearance:none;-webkit-appearance:none;margin-left:auto;align-self:center;padding:5px 12px;border:0;border-radius:999px;background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent);font:600 12.5px var(--sans);letter-spacing:-.005em;font-variant-numeric:tabular-nums;cursor:pointer;transition:background .15s}
.trb:hover{background:color-mix(in srgb,var(--accent) 20%,transparent)}
.tri{position:fixed;inset:0;z-index:25;display:grid;place-items:center;padding:16px;background:color-mix(in srgb,var(--bg) 55%,transparent);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.tri[hidden]{display:none}
.trc{width:min(540px,100%);padding:22px 24px 18px;border-radius:18px;background:color-mix(in srgb,var(--panel) 92%,transparent);backdrop-filter:saturate(180%) blur(24px);-webkit-backdrop-filter:saturate(180%) blur(24px);box-shadow:0 0 0 .5px color-mix(in srgb,var(--ink) 18%,transparent),0 30px 80px -20px rgba(0,0,0,.35);outline:0}
.trh{display:flex;align-items:baseline;gap:10px;font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums}
.trh b{font:600 11.5px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--ink)}
.trh span{margin-left:auto}
.trp{height:2px;margin:12px 0 20px;border-radius:2px;background:var(--line);overflow:hidden}
.trp i{display:block;width:0;height:100%;background:var(--accent);transition:width .3s cubic-bezier(.2,.8,.2,1)}
.trm{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums}
.trm .ln{display:inline-flex;align-items:center;gap:6px;color:var(--ink)}
.trm .ln::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--lc)}
.trm .bad{color:var(--bad);font-weight:500}
.trt{margin:10px 0 22px;font:600 21px/1.3 var(--sans);letter-spacing:-.015em;color:var(--ink);overflow-wrap:anywhere}
.trk{display:flex;flex-wrap:wrap;gap:6px}
.trk button{appearance:none;-webkit-appearance:none;display:flex;align-items:center;justify-content:space-between;gap:8px;flex:1 1 auto;white-space:nowrap;min-height:40px;padding:8px 10px 8px 12px;border:0;border-radius:10px;background:var(--soft);color:var(--ink);font:500 13px var(--sans);text-align:left;cursor:pointer;transition:background .15s}
.trk button:hover{background:color-mix(in srgb,var(--ink) 10%,transparent)}
.trk button.bad{color:var(--bad)}
.trk button:disabled{color:var(--faint);cursor:default}
.trk kbd{flex:none;font:500 11px var(--mono);color:var(--mute);padding:1px 6px;border-radius:5px;box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--ink) 28%,transparent)}
.trf{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:16px;font-size:12px;color:var(--faint)}
.trf button{appearance:none;-webkit-appearance:none;border:0;background:none;padding:0;color:var(--accent);font:500 12.5px var(--sans);cursor:pointer}
.trd{margin:4px 0 6px;font-size:14px;color:var(--mute)}
@media (max-width:760px){.tri{place-items:end center}.trc{padding:20px 18px 16px}.trt{font-size:19px}.trk button{flex-basis:40%}}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
@media (max-width:1180px){.lane{grid-template-columns:280px minmax(0,1fr) minmax(0,1fr)}.wk7{grid-column:1/-1;border-left:0!important;border-top:1px solid var(--line)}}
@media (max-width:900px){.duo{grid-template-columns:1fr}.lnav a{display:none}.lnav a.gear{display:grid}}
@media (max-width:760px){.lane{grid-template-columns:1fr}.lane>div+div{border-left:0;border-top:1px solid var(--line)}
.kpi{grid-template-columns:1fr}.kpi>*+*{border-left:0;border-top:1px solid var(--line)}.kpi>*{padding:20px 22px;flex-direction:row;flex-wrap:wrap;align-items:baseline;gap:4px 12px}
.kpi b{font-size:40px}.kpi strong{margin:0}.kpi span{flex-basis:100%}
.tile{padding:22px 18px}.lane>div{padding:20px 18px}.hero{padding:36px 0 22px}.sec h2{font-size:26px}
.tl .it{flex-wrap:wrap;gap:4px 10px}.its .it{flex-wrap:wrap;gap:4px 10px}.it .lt{order:5}}
@media (prefers-reduced-motion:no-preference){
.kpi,.duo,.block{animation:fade .6s cubic-bezier(.25,.1,.25,1) both}.duo{animation-delay:.05s}.block{animation-delay:.1s}
@keyframes fade{from{opacity:0}}
.g .nd{animation:needle 1.2s cubic-bezier(.22,1,.36,1) .25s both}@keyframes needle{from{left:0}}
.g .fl{animation:trail 1.2s cubic-bezier(.22,1,.36,1) .25s both}@keyframes trail{from{transform:scaleX(0)}}
.tri:not([hidden]) .trc{animation:pop .24s cubic-bezier(.2,.8,.2,1) both}@keyframes pop{from{opacity:0;transform:translateY(10px) scale(.985)}}}
"""


D_JS = '''<script>
(()=>{
const D=document,RM=matchMedia('(prefers-reduced-motion: reduce)');
let pending=null,inflight=0,renaming=false,chain=Promise.resolve(),menuRow=null,menuBtn=null,tt=null,tri=false;
const busy=()=>{window.cockpitBusy=!!(pending||inflight||renaming||menuRow||tri)};
const pad=n=>String(n).padStart(2,'0');
const iso=d=>d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
const plus=n=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+n);return d};
const nextMon=()=>{const w=new Date().getDay()||7;return plus(((8-w)%7)||7)};
const parse=s=>{const a=s.split('-').map(Number);return new Date(a[0],a[1]-1,a[2],12)};
const DN=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const short=d=>DN[d.getDay()]+' '+d.getDate();
const nice=d=>short(d)+' '+MN[d.getMonth()];
function bump(n,by){D.querySelectorAll('[data-n="'+n+'"]').forEach(e=>{const v=Math.max(0,+e.dataset.v+by);e.dataset.v=v;e.textContent=(e.dataset.t||'{}').replace('{}',v)})}
function syncGroups(){const gs=[...D.querySelectorAll('#carried .cg')];gs.forEach(g=>g.hidden=!g.querySelector('.it:not([hidden])'));const e=D.querySelector('#carried .cge');if(e&&gs.length)e.hidden=gs.some(g=>!g.hidden);const th=D.getElementById('think');if(th)th.hidden=!th.querySelector('.it:not([hidden])');D.querySelectorAll('.trb').forEach(b=>b.hidden=!+b.dataset.v)}
function syncDays(){D.querySelectorAll('#days .ag-col').forEach(c=>{const cnt=c.querySelector('.ag-n');if(!cnt)return;
  const all=c.querySelectorAll('.ag-i:not([data-gone])').length,vis=c.querySelectorAll('.ag-i:not([data-gone]):not([hidden])').length;
  if(cnt.dataset.v!=null)cnt.dataset.v=all;cnt.textContent=vis;cnt.hidden=!vis})}
function syncDups(){const b=D.getElementById('dups');if(b)b.hidden=!b.querySelector('.dp:not([hidden])');syncGroups();syncDays()}
function hideRows(rid,cls){
  const q='[data-rid="'+rid+'"]',rows=[...D.querySelectorAll('.it'+q+',.ag-i'+q)],els=rows.concat([...D.querySelectorAll('.dp[data-a="'+rid+'"],.dp[data-b="'+rid+'"]')]);
  const td=iso(plus(0)),due=rows[0]&&rows[0].dataset.due,ns=due&&due<td?['carried','over']:due===td?['today']:[];
  if(due&&due<td){const g=Math.round((parse(td)-parse(due))/864e5);ns.push(g<=7?'g-week':g<=30?'g-slip':'g-stale');if(g>7)ns.push('tri')}
  if(rows.some(r=>r.closest('#think')))ns.push('think');
  ns.forEach(n=>bump(n,-1));els.forEach(e=>e.classList.add(cls));
  const t=setTimeout(()=>{els.forEach(e=>{e.hidden=true;e.setAttribute('data-gone','')});syncDups()},RM.matches?0:400);
  return()=>{clearTimeout(t);els.forEach(e=>{e.classList.remove(cls);e.hidden=false;e.removeAttribute('data-gone')});ns.forEach(n=>bump(n,1));syncDups()};
}
const T=D.createElement('div');T.className='toast';T.setAttribute('role','status');T.setAttribute('aria-live','polite');
T.innerHTML='<span></span><button type="button">Undo</button><i></i>';D.body.appendChild(T);
function toast(msg,undoable,ms){clearTimeout(tt);T.firstChild.textContent=msg;T.classList.toggle('undo',!!undoable);T.classList.remove('run');void T.offsetWidth;T.classList.add('on');
  if(undoable)T.classList.add('run');else tt=setTimeout(hideToast,ms||6000)}
function hideToast(){T.classList.remove('on','run')}
function send(req,keep){return fetch('/api/reminder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req),keepalive:!!keep})
  .then(r=>r.json().catch(()=>({})).then(j=>{if(!r.ok)throw{msg:r.status===409?j.error:r.status===502?j.error:'The cockpit could not make that change.'}}))}
function act(req,msg,undo){if(pending)commit();pending={req,undo,timer:setTimeout(commit,5000)};toast(msg,true);busy()}
function commit(){const p=pending;if(!p)return;pending=null;clearTimeout(p.timer);hideToast();inflight++;busy();
  chain=chain.then(()=>send(p.req)).catch(e=>{if(p.undo)p.undo();toast(e&&e.msg||'Could not save. The local cockpit server is not answering.')}).finally(()=>{inflight--;busy()})}
function undo(){const p=pending;if(!p)return;pending=null;clearTimeout(p.timer);if(p.undo)p.undo();if(p.tri!=null)triBack(p.tri);toast('Undone',false,1600);busy()}
T.querySelector('button').addEventListener('click',undo);
D.addEventListener('keydown',e=>{const c=e.target;if((e.key==='Enter'||e.key===' ')&&c.matches&&c.matches('.ag-i[data-rid]')){e.preventDefault();openMenu(c)}});
D.addEventListener('keydown',e=>{if(pending&&(e.metaKey||e.ctrlKey)&&!e.shiftKey&&e.key.toLowerCase()==='z'&&!e.target.closest('input,textarea,[contenteditable]')){e.preventDefault();undo()}});
addEventListener('pagehide',()=>{if(pending){const p=pending;pending=null;clearTimeout(p.timer);send(p.req,true).catch(()=>{})}});
const M=D.createElement('div');M.className='menu';M.setAttribute('role','menu');M.hidden=true;D.body.appendChild(M);
function place(){const r=menuBtn.getBoundingClientRect(),w=M.offsetWidth,h=M.offsetHeight;let x=Math.min(Math.max(8,r.right-w),innerWidth-w-8),y=r.bottom+6;
  if(y+h>innerHeight-8&&r.top-h-6>8)y=r.top-h-6;M.style.left=x+'px';M.style.top=y+'px'}
function openMenu(btn){
  const row=btn.closest('.it,.ag-i');if(menuRow===row){closeMenu(true);return}
  closeMenu(false);menuRow=row;menuBtn=btn;
  const nr=row.hasAttribute('data-norename'),mi=(a,label,extra,cls)=>'<button type="button" role="menuitem" data-a="'+a+'"'+(cls?' class="'+cls+'"':'')+'>'+label+(extra?'<small>'+extra+'</small>':'')+'</button>';
  M.innerHTML=mi('done','Mark done')+'<hr>'+mi('tom','Tomorrow',short(plus(1)))+mi('nw','Next week',short(nextMon()))+mi('pick','Pick a date…')
    +'<div class="pick" hidden><input type="date" aria-label="New date"><button type="button" data-a="go">Move</button></div>'+(row.dataset.due?mi('nodate','Remove date'):'')
    +(row.closest('#think')?'':canThink()?mi('think','Needs thinking','no date'):'<button type="button" role="menuitem" disabled>Needs thinking<small>add a Think list</small></button>')+'<hr>'
    +(nr?'<button type="button" role="menuitem" disabled>Rename…<small>in Reminders</small></button>':mi('rename','Rename…'))
    +mi('cancel',row.dataset.rec?'Cancel and stop repeating':'Cancel reminder','','bad');
  M.hidden=false;btn.setAttribute('aria-expanded','true');place();M.querySelector('[role=menuitem]').focus();busy();
}
function closeMenu(refocus){if(!menuRow)return;M.hidden=true;menuBtn.setAttribute('aria-expanded','false');if(refocus)menuBtn.focus();menuRow=menuBtn=null;busy()}
M.addEventListener('click',e=>{
  const b=e.target.closest('button[data-a]');if(!b||b.disabled)return;const row=menuRow,a=b.dataset.a,td=iso(plus(0));
  if(a==='pick'){const p=M.querySelector('.pick'),inp=p.querySelector('input');p.hidden=false;inp.min=td;inp.value=row.dataset.due>=td?row.dataset.due:iso(plus(1));
    place();inp.focus();try{inp.showPicker()}catch(_){}return}
  if(a==='go'){const v=M.querySelector('.pick input').value;if(!v||v<td)return;closeMenu(true);move(row,v);return}
  closeMenu(a!=='rename');
  ({done,tom:r=>move(r,iso(plus(1))),nw:r=>move(r,iso(nextMon())),nodate,think,rename,cancel})[a](row);
});
M.addEventListener('mouseover',e=>{const b=e.target.closest('[role=menuitem]:not([disabled])');if(b&&D.activeElement!==b&&!M.querySelector('.pick input:focus'))b.focus()});
M.addEventListener('keydown',e=>{
  const its=[...M.querySelectorAll('[role=menuitem]:not([disabled])')],i=its.indexOf(D.activeElement),n=its.length;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(e.target.matches('input'))return;e.preventDefault();const d=e.key==='ArrowDown'?1:-1;its[i<0?(d>0?0:n-1):(i+d+n)%n].focus()}
  else if(e.key==='Escape'){e.preventDefault();closeMenu(true)}
  else if(e.key==='Enter'&&e.target.matches('.pick input')){e.preventDefault();M.querySelector('[data-a=go]').click()}
  else if(e.key==='Tab'&&!(e.target.closest('.pick')&&!(e.target.dataset.a==='go'&&!e.shiftKey))){e.preventDefault();closeMenu(true)}
});
D.addEventListener('pointerdown',e=>{if(menuRow&&!M.contains(e.target)&&e.target.closest('.mo,.ag-i[data-rid]')!==menuBtn)closeMenu(false)},true);
addEventListener('scroll',()=>{if(menuRow&&!M.contains(D.activeElement))closeMenu(false)},{passive:true});
addEventListener('resize',()=>closeMenu(false));
D.addEventListener('click',e=>{if(e.target.closest('input'))return;const t=e.target.closest('.ck,.mo,.keep,.trb,.ag-i[data-rid]');if(!t)return;e.preventDefault();
  if(t.classList.contains('ag-i'))openMenu(t);
  else if(t.classList.contains('ck')){const r=t.closest('.it,.ag-i');if(menuRow===r)closeMenu(false);done(r)}else if(t.classList.contains('mo'))openMenu(t);else if(t.classList.contains('trb'))triStart(t);else keep(t)});
// The name in the bar goes back to the top and drops a plain section anchor (#lanes) from the address; #days?... filters stay.
D.addEventListener('click',e=>{const a=e.target.closest('a.home');if(!a||e.metaKey||e.ctrlKey||e.shiftKey)return;e.preventDefault();
  if(location.hash&&!location.hash.startsWith('#days?'))history.replaceState(null,'',location.pathname+location.search);
  scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'})});
// Linear issues open in the Linear app (linear:// is the same address); Cmd-click still opens the website.
const LW='https://linear.app/',appUrl=u=>u.startsWith(LW)?'linear://'+u.slice(LW.length):null;
const openLinear=u=>{const a=appUrl(u);if(a)location.href=a;else window.open(u,'_blank','noopener')};
D.addEventListener('click',e=>{const a=e.target.closest('a[href^="https://linear.app/"]');
  if(!a||e.defaultPrevented||e.button||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();openLinear(a.href)});
function done(row){act({action:'done',id:row.dataset.rid},'Marked done',hideRows(row.dataset.rid,'leaving'))}
function cancel(row){act({action:'cancel',id:row.dataset.rid},row.dataset.rec?'Cancelled, no longer repeats':'Cancelled',hideRows(row.dataset.rid,'leaving'))}
function nodate(row){act({action:'nodate',id:row.dataset.rid},'Date removed',hideRows(row.dataset.rid,'moving'))}
function think(row){act({action:'think',id:row.dataset.rid},'Moved to Needs thinking',hideRows(row.dataset.rid,'moving'))}
const TR=D.createElement('div');TR.className='tri';TR.hidden=true;TR.setAttribute('role','dialog');TR.setAttribute('aria-modal','true');TR.setAttribute('aria-label','Triage carried over');
TR.innerHTML='<div class="trc" tabindex="-1"><div class="trh"><b>Triage</b><span></span></div><div class="trp"><i></i></div><div class="trbd"></div></div>';D.body.appendChild(TR);
const TK={done:['D','Done'],tom:['T','Tomorrow'],nw:['W','Next week'],nodate:['S','Someday'],think:['K','Needs thinking'],cancel:['C','Cancel'],skip:['N','Skip'],open:['O','Open in Linear']};
let triQ=[],triI=0,triDone=0,triSkip=0,triRet=null;
const canThink=()=>!!D.querySelector('.wrap[data-think]');
function triRows(){const lim=iso(plus(-7)),seen=new Set();
  return [...D.querySelectorAll('#carried .it')].filter(r=>!r.hidden&&r.dataset.due&&r.dataset.due<lim).filter(r=>{const k=r.dataset.rid||r.dataset.url||r.textContent;if(seen.has(k))return false;seen.add(k);return true})
    .sort((a,b)=>(!a.dataset.rid-!b.dataset.rid)||(a.dataset.due<b.dataset.due?-1:a.dataset.due>b.dataset.due?1:0))}
function triShow(){
  const n=triQ.length,c=TR.querySelector('.trc'),bd=c.querySelector('.trbd');
  c.querySelector('.trh span').textContent=Math.min(triI+1,n)+' of '+n;c.querySelector('.trp i').style.width=(Math.min(triI,n)/n*100)+'%';
  if(triI>=n){bd.innerHTML='<p class="trt">All caught up</p><p class="trd"></p><div class="trf"><span>Skipped ones stay in Carried over.</span><button type="button" data-k="close">Close</button></div>';
    bd.querySelector('.trd').textContent=triDone+' handled, '+triSkip+' skipped.';bd.querySelector('[data-k=close]').focus();return}
  const r=triQ[triI],rem=!!r.dataset.rid,lc=[...r.classList].find(x=>x.startsWith('l-'))||'',lt=r.querySelector('.lt'),days=Math.round((parse(iso(plus(0)))-parse(r.dataset.due))/864e5),ok=canThink();
  const ks=rem?['done','tom','nw','nodate','think','cancel','skip']:['open','skip'];
  bd.innerHTML='<div class="trm"><span class="ln '+lc+'"></span><span class="bad">'+days+'d late</span><span>'+(rem?'Reminder':'Linear, read only here')+'</span></div><p class="trt"></p><div class="trk">'
    +ks.map(k=>'<button type="button" data-k="'+k+'"'+(k==='cancel'?' class="bad"':'')+(k==='think'&&!ok?' disabled title="Add a list called Think in Reminders first"':'')+'>'+TK[k][1]+'<kbd>'+TK[k][0]+'</kbd></button>').join('')
    +'</div><div class="trf"><span>'+(rem?'Z undoes the last one for 5 seconds. Esc closes.':'Esc closes.')+'</span><button type="button" data-k="close">Close</button></div>';
  bd.querySelector('.ln').textContent=lt?lt.textContent:'';bd.querySelector('.trt').textContent=(r.querySelector('.tt')||r).textContent;
  if(!TR.contains(D.activeElement)||D.activeElement.closest('.trbd'))c.focus();
}
function triAct(k){
  if(k==='close')return triClose();
  const r=triQ[triI];if(!r)return;
  if(k==='skip'){triSkip++;triI++;return triShow()}
  if(k==='open'){if(r.dataset.url)openLinear(r.dataset.url);return}
  if(!r.dataset.rid||(k==='think'&&!canThink()))return;
  const p0=pending,i=triI;
  ({done,tom:x=>move(x,iso(plus(1))),nw:x=>move(x,iso(nextMon())),nodate,think,cancel})[k](r);
  if(pending&&pending!==p0)pending.tri=i;
  triDone++;triI++;triShow();
}
function triBack(i){if(!tri)return;triSkip=Math.max(0,triSkip-Math.max(0,triI-i-1));triDone=Math.max(0,triDone-1);triI=i;triShow()}
function triStart(btn){triQ=triRows();if(!triQ.length)return;closeMenu(false);triI=triDone=triSkip=0;triRet=btn;tri=true;TR.hidden=false;D.documentElement.style.overflow='hidden';triShow();busy()}
function triClose(){if(!tri)return;tri=false;TR.hidden=true;D.documentElement.style.overflow='';if(pending)delete pending.tri;if(triRet&&!triRet.hidden)triRet.focus();triRet=null;busy()}
TR.addEventListener('click',e=>{const b=e.target.closest('button[data-k]');if(b){if(!b.disabled)triAct(b.dataset.k)}else if(e.target===TR)triClose()});
TR.addEventListener('keydown',e=>{
  if(e.key==='Escape'){e.preventDefault();triClose();return}
  if(e.key==='Tab'){const f=[...TR.querySelectorAll('button:not(:disabled)')],i=f.indexOf(D.activeElement);if(!f.length)return;
    if(e.shiftKey&&i<=0){e.preventDefault();f[f.length-1].focus()}else if(!e.shiftKey&&i===f.length-1){e.preventDefault();f[0].focus()}return}
  if(e.metaKey||e.ctrlKey||e.altKey)return;
  const k=e.key.toLowerCase();
  if(k==='z'){e.preventDefault();if(pending)undo();return}
  const m={d:'done',t:'tom',w:'nw',s:'nodate',k:'think',c:'cancel',n:'skip',o:'open'}[k];if(!m)return;
  const b=TR.querySelector('.trk [data-k="'+m+'"]');if(b&&!b.disabled){e.preventDefault();triAct(m)}
});
function move(row,date){if(date===row.dataset.due)return;const w=row.dataset.when,td=iso(plus(0));
  act({action:'move',id:row.dataset.rid,due:w?date+' '+w:date},date===td?'Moved to today':date===iso(plus(1))?'Moved to tomorrow':'Moved to '+nice(parse(date)),hideRows(row.dataset.rid,'moving'))}
function keep(b){act({action:'cancel',id:b.dataset.drop,keep:b.dataset.keep},'Duplicate cancelled',hideRows(b.dataset.drop,'leaving'))}
function rename(row){
  const t=row.querySelector('.tt,.t'),old=t.textContent,rid=row.dataset.rid,inp=D.createElement('input');
  inp.className='rn';inp.maxLength=300;inp.value=old;inp.setAttribute('aria-label','Reminder title');
  t.textContent='';t.appendChild(inp);inp.focus();inp.select();renaming=true;busy();let fin=false;
  const set=s=>D.querySelectorAll('.it[data-rid="'+rid+'"] .tt,.dq[data-rid="'+rid+'"] .tt,.ag-i[data-rid="'+rid+'"] .t').forEach(e=>e.textContent=s);
  const end=(save,refocus)=>{if(fin)return;fin=true;renaming=false;const v=inp.value.trim();t.textContent=old;
    if(save&&v&&v!==old){set(v);act({action:'rename',id:rid,title:v},'Renamed',()=>set(old))}else busy();
    if(refocus)(row.querySelector('.mo')||row).focus()};
  inp.addEventListener('keydown',e=>{e.stopPropagation();if(e.key==='Enter'){e.preventDefault();end(true,true)}else if(e.key==='Escape'){e.preventDefault();end(false,true)}});
  inp.addEventListener('blur',()=>end(false,false));
}
syncDups();
})();
</script>'''


def gauge_rows(i):
    z = R.pos(STALE) / R.SPAN * 100
    ticks = "".join(f'<span class="tk{" z" if t == STALE else ""}" style="left:{R.pos(t) / R.SPAN * 100:.2f}%"></span>'
                    for t in sorted(set(R.TICKS) | {STALE}))
    out = []
    for s, a in i["ages"].items():
        if a is None:
            out.append(f'<li><span>{s}</span><i class="g" style="--z:{z:.2f}%">{ticks}</i><em class="bad">never</em></li>')
            continue
        bad = "bad" if a > STALE else ""
        p = R.pos(a) / R.SPAN * 100
        out.append(f'<li><span>{s}</span><i class="g" style="--z:{z:.2f}%" title="{s}: {ago(a)} since last touched">{ticks}'
                   f'<span class="fl" style="width:{p:.2f}%"></span><span class="nd {bad}" style="left:{p:.2f}%"></span></i>'
                   f'<em class="{bad}">{ago(a)}</em></li>')
    return "".join(out)

ON = SRC.load()
try:
    EXTRAS = json.loads((ROOT / "data" / "extras.json").read_text()).get("sources", {})
except (OSError, ValueError):
    EXTRAS = {}


def days_since(iso):
    return (TODAY - dt.date.fromisoformat(iso)).days


def pr_row(p):
    quiet = days_since(p["updated"])
    lane = p["lane"] if p["lane"] in SHORT else ""
    name = p["repo"].split("/", 1)[1]
    late = (f'<span class="late" title="No activity for {quiet} days">quiet {quiet}d</span>' if quiet > STALE
            else f'<span class="late ok" title="Last activity">active {quiet}d</span>')
    return (f'<li class="it{" l-" + lane if lane else ""}"><a href="{esc(p["url"])}" target="_blank" rel="noopener">'
            f'<span class="ico pr"></span><span class="tt">{"Draft: " if p["draft"] else ""}{clean(p["title"])}'
            f'<small>{clean(name)} #{p["number"]}</small></span></a>'
            f'<span class="w" title="Opened {p["created"]}">{days_since(p["created"])}d old</span>{late}</li>')


def pr_list(items, none):
    if not items:
        return f'<p class="empty">{none}</p>'
    items = sorted(items, key=lambda p: p["updated"])  # longest quiet first
    head = "".join(pr_row(p) for p in items[:6])
    rest = items[6:]
    more = f'<details><summary>{len(rest)} more</summary><ul class="its">{"".join(pr_row(p) for p in rest)}</ul></details>' if rest else ""
    return f'<ul class="its">{head}</ul>{more}'


def prs_block():
    """GitHub pull requests waiting on you. Absent from the page when the source is off."""
    if not ON["github_prs"]:
        return ""
    src = EXTRAS.get("github_prs")
    if src is None:
        return ('<div class="block" id="prs"><div class="sec"><h2>Pull requests</h2><span class="chip">Test</span></div>'
                '<section class="tile"><p class="empty">Loads on the next refresh.</p></section></div>')
    items = [p for p in src["items"] if ON["github_prs_bs"] or p["lane"] != "bs"]
    review = [p for p in items if p["kind"] == "review"]
    mine = [p for p in items if p["kind"] == "mine"]
    stale = sum(1 for p in items if days_since(p["updated"]) > STALE)
    q = (f'<p class="qline">Could not read {clean("; ".join(src["errors"]))}. Everything else still loads.</p>'
         if src["errors"] else "")
    scope = "Axis and your own repos" + (", plus Blvck Sigma" if ON["github_prs_bs"] else "")
    # An empty column is not drawn: its "none" moves into the line under the heading.
    cols = [(t, l) for t, l in (("Review requested", review), ("Yours", mine)) if l]
    none = " ".join(x for x, l in (("No reviews requested.", review), ("No open PRs of yours.", mine)) if not l)
    line = f"Open PRs in {scope}. " + (f"{stale} of {len(items)} with no activity for over {STALE} days. " if items else "") + none
    body = "".join(f'<div><h4>{t} <b>{len(l)}</b></h4>{pr_list(l, "")}</div>' for t, l in cols)
    grid = f'<section class="tile prs"><div class="prt{" one" if len(cols) == 1 else ""}">{body}</div>{q}</section>' if cols else (
        f'<section class="tile prs">{q}</section>' if q else "")
    return (f'<div class="block" id="prs"><div class="sec"><h2>Pull requests</h2><span class="chip">Test</span>'
            f'<p>{line.strip()}</p></div>{grid}</div>')


def since(iso):
    sec = max(0, (dt.datetime.now().astimezone() - dt.datetime.fromisoformat(iso)).total_seconds())
    return f"{int(sec // 60)}m" if sec < 3600 else f"{int(sec // 3600)}h" if sec < 86400 else f"{int(sec // 86400)}d"


def session_row(x):
    lane = x["lane"] if x.get("lane") in SHORT else ""
    small = clean(x["folder"] or "no folder") + (" &middot; side session" if x.get("side") else "")
    return (f'<li class="it{" l-" + lane if lane else ""}"><a href="claude://claude.ai/epitaxy/{esc(x["id"])}" title="Open in the Claude app">'
            f'<span class="ico pr"></span><span class="tt">{clean(x["title"] or "Untitled session")}<small>{small}</small></span></a>'
            f'<span class="late ok" title="Last activity {esc(x["last"][:16].replace("T", " "))}">{since(x["last"])} ago</span></li>')


def sessions_block():
    """Recent Claude Code sessions from the desktop app's files, with an Open link. Absent from the page when the source is off."""
    if not ON["claude_sessions"]:
        return ""
    head = '<div class="block" id="claude"><div class="sec"><h2>Claude sessions</h2><span class="chip">Test</span>'
    src = EXTRAS.get("claude_sessions")
    if src is None:
        return head + '</div><section class="tile"><p class="empty">Loads on the next refresh.</p></section></div>'
    items = src.get("items") or []
    if not items and src.get("errors"):
        return head + f'<p>Could not read {clean("; ".join(src["errors"]))}. Everything else still loads.</p></div></div>'
    days = src.get("days", 7)
    line = (f"{len(items)} sessions active in the last {days} days, newest first. Scheduled runs and archived sessions are left out. "
            "Open jumps to the session in the Claude app.")
    if not items:
        return head + f'<p>No sessions active in the last {days} days.</p></div></div>'
    rows = "".join(session_row(x) for x in items[:8])
    rest = items[8:]
    more = f'<details><summary>{len(rest)} more</summary><ul class="its">{"".join(session_row(x) for x in rest)}</ul></details>' if rest else ""
    q = f'<p class="qline">{clean("; ".join(src["errors"]))}.</p>' if src.get("errors") else ""
    return head + f'<p>{line}</p></div><section class="tile prs cs"><ul class="its">{rows}</ul>{more}{q}</section></div>'


def hfmt(sec):
    return f"{sec / 3600:.1f}"


def rize_block():
    """Rize tracked time per lane, this week so far against last week. Absent from the page when the source is off."""
    if not ON["rize"]:
        return ""
    head = '<div class="block" id="rize"><div class="sec"><h2>Tracked time</h2><span class="chip">Test</span>'
    src = EXTRAS.get("rize")
    if src is None:
        return head + '</div><section class="tile"><p class="empty">Loads on the next refresh.</p></section></div>'
    weeks = src.get("weeks")
    if not weeks:  # one quiet line, no tile
        err = "; ".join(src.get("errors") or ["no data"])
        return head + f'<p>Could not read {clean(err)}. Everything else still loads.</p></div></div>'
    th, la = weeks["this"]["seconds"], weeks["last"]["seconds"]
    rows = [(i["key"], clean(i["short"]), i["budget"]) for i in INFO]
    extra = [("unmatched", "No lane for project", None), ("none", "No project in Rize", None)]
    rows += [r for r in extra if th.get(r[0]) or la.get(r[0])]
    top = max([th.get(k, 0) for k, _, _ in rows] + [la.get(k, 0) for k, _, _ in rows]
              + [b * 3600 for _, _, b in rows if b] + [3600])
    pct = lambda sec: min(sec / top * 100, 100)  # noqa: E731
    lis = []
    for k, name, budget in rows:
        a, b = th.get(k, 0), la.get(k, 0)
        cls = f"l-{k}" if k in SHORT else "x"
        over = budget and a > budget * 3600
        marks = f'<span class="pv" style="left:{pct(b):.2f}%" title="Last week {hfmt(b)} h"></span>' if b else ""
        if budget:
            marks += f'<span class="bg" style="left:{pct(budget * 3600):.2f}%" title="Budget {budget} h a week"></span>'
        lis.append(f'<li class="{cls}{" zero" if not a and not b else ""}"><span class="nm">{name}</span>'
                   f'<span class="tr"><span class="fl{" over" if over else ""}" style="width:{pct(a):.2f}%"></span>{marks}</span>'
                   f'<b>{hfmt(a)}</b><em>{hfmt(b)}</em></li>')
    days = TODAY.weekday() + 1
    line = (f"From Rize: {hfmt(weeks['this']['total'])} h since Monday ({days} of 7 days), "
            f"{hfmt(weeks['last']['total'])} h last week. The bar is this week, the tick is last week"
            + (", the ring is the weekly budget." if any(b for _, _, b in rows) else "."))
    if not weeks["this"]["total"] and TODAY.weekday() > 0:  # a whole weekday with nothing is a tracking problem, not a quiet week
        line = (f"Rize has no time since Monday, {hfmt(weeks['last']['total'])} h last week. "
                "If you worked this week, check that Rize is tracking and signed in.")
    q = f'<p class="qline">Could not read {clean("; ".join(src["errors"]))}.</p>' if src.get("errors") else ""
    hint = ('<p class="qline">A Rize project with no lane can be mapped in config.json under rize_projects.</p>'
            if th.get("unmatched") or la.get("unmatched") else "")
    return (head + f'<p>{line}</p></div><section class="tile rz"><ul class="rzl">'
            f'<li class="hd"><span></span><span></span><b>This week</b><em>Last week</em></li>{"".join(lis)}</ul>{q}{hint}</section></div>')


GEAR = ('<a class="gear" href="settings.html" aria-label="Settings" title="Settings"><svg viewBox="0 0 24 24" aria-hidden="true">'
        '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 '
        '1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 '
        '1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 '
        '2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 '
        '1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></a>')


def build_d():
    global ACT
    ACT = LIVE
    R.ACT = LIVE  # Day by day cards act too
    today = COLS[TODAY]
    over = COLS["over"]
    anytime = [x for x in today if not x["when"]]
    timed = [x for x in today if x["when"]]
    rows = []
    if anytime:
        rows.append('<li class="anytime">All day</li>' + "".join(item(x, lane_tag=False) for x in anytime))
    placed = False
    nowli = f'<li class="now">{NOW_HM}<i></i></li>'
    for x in timed:
        if not placed and x["when"] >= NOW_HM:
            rows.append(nowli)
            placed = True
        rows.append(item(x, lane_tag=False))
    if not placed:
        rows.append(nowli)
    frac = lambda t: R.pos(t) / R.SPAN  # noqa: E731
    keep = sorted({0, STALE, R.TICKS[-1]})  # zero, the stale mark and the end always labelled
    for t in R.TICKS:  # other labels only where they have room (12% of the track)
        if t not in keep and all(abs(frac(t) - frac(k)) >= 0.12 for k in keep):
            keep = sorted(keep + [t])
    scale = '<li class="sc"><span>days</span><i>' + "".join(f'<b style="left:{R.pos(t) / R.SPAN * 100:.2f}%">{t}</b>' for t in keep) + '</i><em></em></li>'
    lanes_html = []
    vis = {x["key"] for x in ST.layout() if x["visible"]}  # links point only at sections that are shown
    days_on = "days" in vis
    for i in INFO:
        waiting = sorted(i["waiting"], key=lambda x: x.get("date") or "")
        ov = sorted(i["overdue"], key=lambda x: x.get("due") or "")
        lanes_html.append(f"""<section class="lane l-{i['key']} {i['state']}" id="lane-{i['key']}">
<div class="who"><h3>{clean(i['short'])}</h3><p class="stw">{clean(state_word(i))}</p><ul class="gg">{gauge_rows(i)}{scale}</ul></div>
<div><h4>Next</h4>{nx(i)}</div>
<div><h4>Waiting on you <b>{len(waiting)}</b></h4>{mini(waiting, "date", False)}<h4>Overdue <b>{len(ov)}</b></h4>{mini(ov, "due", True)}</div>
<div class="wk7">{re.sub(r"<span>(\w\w) (\d+)</span>", r"<span><small>\1</small>\2</span>", week7(i, link=days_on).replace("<h3>Next 7 days</h3>", "<h4>Next 7 days</h4>"))}</div></section>""")
    lane_filter = ('<div class="lf" role="group" aria-label="Show lane"><button type="button" data-lane="" aria-pressed="true">All lanes</button>'
                   + "".join(f'<button type="button" class="l-{i["key"]}" data-lane="{i["key"]}" aria-pressed="false"><i></i>{clean(i["short"])}</button>' for i in INFO)
                   + "</div>")
    quiet = [i for i in INFO if i["state"] != "active"]
    wait1 = next((i for i in INFO if i["waiting"]), None)
    lanes_on = "lanes" in vis
    # Summary tiles: each opens the section behind its number. Overdue goes to Carried over, Waiting on you to the
    # first lane with something waiting, Lanes going quiet to the first quiet lane (each quiet lane's name to its own).
    t_over = f'<b data-n="over" data-v="{TOT_OVER}">{TOT_OVER}</b><strong>Overdue</strong><span>Reminders and Linear issues past their due date</span>'
    t_over = f'<a class="red" href="#carried">{t_over}</a>' if "today" in vis else f'<div class="red">{t_over}</div>'
    t_wait = f'<b>{TOT_WAIT}</b><strong>Waiting on you</strong><span>Issues started or in review that need your move</span>'
    t_wait = f'<a href="#lane-{wait1["key"]}">{t_wait}</a>' if lanes_on and wait1 else f"<div>{t_wait}</div>"
    if lanes_on and quiet:
        names = ", ".join(f'<a href="#lane-{i["key"]}">{clean(i["short"])}</a>' for i in quiet)
        t_quiet = (f'<div class="st"><b>{QUIET}<small>of {len(INFO)}</small></b><strong><a class="cover" href="#lane-{quiet[0]["key"]}">Lanes going quiet</a></strong>'
                   f"<span>{names}</span></div>")
    else:
        t_quiet = f'<div><b>{QUIET}<small>of {len(INFO)}</small></b><strong>Lanes going quiet</strong><span>{", ".join(clean(i["short"]) for i in quiet) or "none"}</span></div>'
    groups = [("week", "This week", "up to 7 days late", 6, lambda d: d <= 7),
              ("slip", "Slipping", "8 to 30 days late", 4, lambda d: 7 < d <= 30),
              ("stale", "Stale", "over 30 days late", 3, lambda d: d > 30)]
    carried = []
    for key, label, sub, first, fits in groups:
        its = [it for it in over if fits((TODAY - it["due"]).days)]
        if its:
            carried.append(f'<div class="cg" data-g="{key}"><h3>{label} <small>{sub}</small><b data-n="g-{key}" data-v="{len(its)}" data-t="{{}}">{len(its)}</b></h3>'
                           f'{listing(its, first, late=True)}</div>')
    carried = "".join(carried) + f'<p class="empty cge"{" hidden" if carried else ""}>Nothing</p>'
    late7 = sum(1 for it in over if (TODAY - it["due"]).days > 7)
    trb = (f'<button class="trb" type="button" aria-haspopup="dialog" data-n="tri" data-v="{late7}" data-t="Triage {{}}">Triage {late7}</button>'
           if ACT and late7 else "")
    think = ""
    if ACT and THINK_ITEMS:
        n = len(THINK_ITEMS)
        think = (f'<div class="block dupb" id="think"><div class="sec"><h2>Needs thinking</h2>'
                 f'<p><span data-n="think" data-v="{n}" data-t="{{}}">{n}</span> parked with no date. Give one a date and it goes back to its list.</p></div>'
                 f'<section class="tile">{listing(THINK_ITEMS, 6)}</section></div>')
    sections = {
        "kpi": f'<div class="kpi">{t_over}\n{t_wait}\n{t_quiet}</div>',
        "today": f"""<div class="duo" id="today">
<section class="tile"><div class="th"><h2>Today</h2><span data-n="today" data-v="{len(today)}" data-t="{{}} items">{len(today)} items</span></div><ol class="tl">{"".join(rows)}</ol></section>
<section class="tile" id="carried"><div class="th"><h2>Carried over</h2><span data-n="carried" data-v="{len(over)}" data-t="{{}} past due">{len(over)} past due</span>{trb}</div>{carried}</section></div>""",
        "think": think,
        "dups": dups_block() if ACT else "",
        "lanes": f"""<div class="block" id="lanes"><div class="sec"><h2>Lanes</h2><p>Each gauge reads days since you last touched that source. The red zone starts at {STALE} days.</p></div>
<div class="lanes">{"".join(lanes_html)}</div></div>""",
        "prs": prs_block(),
        "rize": rize_block(),
        "claude": sessions_block(),
        "days": f'<div class="block" id="days"><div class="sec"><h2>Day by day</h2>{lane_filter}</div><section class="tile">{R.agenda()}</section></div>',
        "hours": f'<div class="block" id="hours"><div class="sec"><h2>Hours</h2><p>Next 7 days of calendar, booked against each lane\'s weekly budget.</p></div><section class="tile">{R.week()}</section></div>',
    }
    shown = [x["key"] for x in ST.layout() if x["visible"] and sections.get(x["key"])]
    names = {"today": "Today", "think": "Think", "lanes": "Lanes", "prs": "Pull requests", "rize": "Tracked", "claude": "Sessions", "days": "Day by day", "hours": "Hours"}
    links = "".join(f'<a href="#{k}">{names[k]}</a>' for k in shown if k in names)
    body = f"""<nav class="lnav" aria-label="Sections"><div><b><a class="home" href="#top" title="Back to the top">Work Cockpit</a></b>{links}<span>Updated {clean(GEN[11:])}</span>{GEAR}</div></nav>
<div class="wrap"{' data-think="1"' if THINK else ''}>
<header class="hero"><p>Week {WEEKNO}</p><h1>{TODAY.strftime("%A")}, {TODAY.day} {TODAY.strftime("%B")}</h1></header>
{chr(10).join(sections[k] for k in shown)}
<p class="foot">Reminder changes go straight to Apple Reminders. Linear, Calendar and GitHub are read only. Sources, sections and lanes are in <a href="settings.html">Settings</a>. Snapshot {clean(GEN)}.</p>
</div>{D_JS if ACT else ""}{D_LINKS_JS}"""
    page("d", "Precision", "", D_CSS, body)


D_LINKS_JS = '''<script>
(()=>{
const D=document,box=D.getElementById('days'),lf=box&&box.querySelector('.lf');if(!lf)return;
const RM=matchMedia('(prefers-reduced-motion: reduce)'),names={};let day='';
lf.querySelectorAll('button[data-lane]').forEach(b=>{if(b.dataset.lane)names[b.dataset.lane]=b.textContent});
function apply(lane,scroll){
  lf.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.lane===lane)));
  box.querySelectorAll('.ag-col').forEach(c=>{
    let n=0;
    c.querySelectorAll('.ag-i').forEach(i=>{const on=(!lane||i.dataset.lane===lane)&&!i.hasAttribute('data-gone');i.hidden=!on;if(on)n++});
    c.querySelectorAll('details').forEach(d=>{
      if(lane&&!d.open){d.open=true;d.setAttribute('data-lf','')}
      else if(!lane&&d.hasAttribute('data-lf')){d.open=false;d.removeAttribute('data-lf')}});
    c.querySelectorAll('ul,details').forEach(u=>{u.hidden=!!lane&&!u.querySelector('.ag-i:not([hidden])')});
    const cnt=c.querySelector('.ag-n');
    if(cnt){if(cnt.dataset.v==null)cnt.dataset.v=c.querySelectorAll('.ag-i:not([data-gone])').length;cnt.textContent=lane?n:cnt.dataset.v;cnt.hidden=!!lane&&!n}
    let e=c.querySelector('.lf-e');
    if(lane&&!n&&c.querySelector('.ag-i')){if(!e){e=D.createElement('p');e.className='empty lf-e';c.appendChild(e)}e.textContent='Nothing for '+names[lane]}
    else if(e)e.remove();
    const pick=!!day&&c.dataset.day===day;c.classList.toggle('pick',pick);
    if(pick)c.style.setProperty('--pick',lane?'var(--'+lane+')':'var(--accent)');else c.style.removeProperty('--pick');
  });
  if(scroll)requestAnimationFrame(()=>{
    const col=day&&box.querySelector('.ag-col[data-day="'+day+'"]');
    (col&&innerWidth<=640?col:box).scrollIntoView({behavior:RM.matches?'auto':'smooth',block:'start'})});
}
function read(scroll){
  const h=location.hash;
  if(h==='#days'){day='';apply('',false);return}
  if(!h.startsWith('#days?'))return;
  const q=new URLSearchParams(h.slice(6)),lane=q.get('lane')||'',d=q.get('day')||'';
  day=/^(\\d{4}-\\d{2}-\\d{2}|over)$/.test(d)?d:'';
  apply(names[lane]?lane:'',scroll);
}
lf.addEventListener('click',e=>{const b=e.target.closest('button[data-lane]');if(!b)return;
  const lane=b.dataset.lane,q=[lane&&'lane='+lane,day&&'day='+day].filter(Boolean).join('&');
  history.replaceState(null,'',q?'#days?'+q:'#days');apply(lane,false)});
D.addEventListener('click',e=>{const a=e.target.closest('a.cell[href^="#days?"]');if(!a||e.metaKey||e.ctrlKey||e.shiftKey)return;
  e.preventDefault();history.pushState(null,'',a.getAttribute('href'));read(true)});
addEventListener('hashchange',()=>read(false));
const nav=performance.getEntriesByType('navigation')[0];
read(!(nav&&nav.type==='reload'));
})();
</script>'''


SETTINGS_CSS = """
.wrap.set{max-width:680px}
.set .hero{padding-bottom:8px}
.lnav output{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;transition:opacity .3s}
.lnav output.bad{color:var(--bad)}
.lnav a.back{display:inline-flex;align-items:center;gap:4px;font-size:13px;color:var(--accent)}
.lnav a.back:hover{color:var(--accent);text-decoration:underline}
.lnav a.back svg{width:8px;height:13px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.gt{display:flex;align-items:center;gap:10px;margin:40px 0 10px;padding:0 4px}
.gt h2{font:600 20px/1.2 var(--disp);letter-spacing:-.02em;margin:0}
ul.grp{display:block;list-style:none;margin:0;padding:0;background:var(--panel);border-radius:14px;box-shadow:var(--sh)}
.row{display:flex;align-items:center;gap:12px;min-height:50px;padding:7px 16px;position:relative;background:var(--panel)}
.row:first-child{border-radius:14px 14px 0 0}
.row:last-child{border-radius:0 0 14px 14px}
.row:only-child{border-radius:14px}
.row+.row::before{content:"";position:absolute;top:0;left:16px;right:0;border-top:1px solid var(--line)}
.row.ind{padding-left:40px}
.row.ind::before{left:40px}
.sname{flex:1;min-width:0;font-size:15px;line-height:1.3;color:var(--ink)}
.sname small{display:block;font-size:12.5px;line-height:1.35;color:var(--mute);margin-top:2px}
.sname small[hidden]{display:none}
.row.off .sname{color:var(--mute)}
.note{margin:8px 0 0;padding:0 16px;font-size:12.5px;line-height:1.45;color:var(--mute)}
.sw{appearance:none;-webkit-appearance:none;margin:0;flex:none;width:38px;height:22px;border-radius:999px;background:color-mix(in srgb,var(--ink) 16%,transparent);position:relative;cursor:pointer;transition:background .2s}
.sw::after{content:"";position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);transition:transform .22s cubic-bezier(.25,.1,.25,1)}
.sw:checked{background:var(--ok)}
.sw:checked::after{transform:translateX(16px)}
.sw:disabled{opacity:.4;cursor:default}
.gr{flex:none;display:grid;place-items:center;width:22px;height:32px;margin-left:-6px;color:var(--faint);cursor:grab;touch-action:none;border-radius:6px}
.gr:hover{color:var(--mute)}
.gr svg{width:10px;height:16px;fill:currentColor}
.ord{flex:none;display:flex;gap:2px}
.ord button{display:grid;place-items:center;width:28px;height:28px;padding:0;border:0;border-radius:8px;background:transparent;color:var(--mute);cursor:pointer}
.ord button:hover:not(:disabled){background:var(--soft);color:var(--ink)}
.ord button:disabled{opacity:.25;cursor:default}
.ord svg{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.row.lift{z-index:2;box-shadow:0 10px 30px rgba(0,0,0,.14),0 0 0 1px var(--line);border-radius:12px;cursor:grabbing}
.row.lift::before,.row.lift+.row::before{display:none}
body.dragging,body.dragging *{cursor:grabbing!important;user-select:none;-webkit-user-select:none}
.ld{flex:none;width:10px;height:10px;border-radius:50%;background:var(--lc)}
.tx{flex:1;min-width:0;font:inherit;font-size:15px;color:var(--ink);background:transparent;border:0;border-radius:8px;padding:6px 8px;margin:0 0 0 -8px}
.tx:hover{background:var(--soft)}
.tx:focus{background:var(--soft);outline:none}
.tx:focus-visible{outline:2px solid var(--accent);outline-offset:0}
.hb{flex:none;display:flex;align-items:center;gap:6px;font-size:13px;color:var(--mute);white-space:nowrap}
.hb input{width:62px;font:inherit;font-size:15px;color:var(--ink);text-align:right;font-variant-numeric:tabular-nums;background:var(--soft);border:0;border-radius:8px;padding:6px 8px}
.hb input::placeholder{color:var(--faint);font-size:13px}
.hb input.wide{width:92px}
.step{flex:none;display:inline-flex;align-items:center;background:var(--soft);border-radius:9px}
.step button{width:34px;height:30px;padding:0;border:0;background:transparent;color:var(--ink);font:500 18px/1 var(--sans);cursor:pointer;border-radius:9px}
.step button:hover:not(:disabled){background:color-mix(in srgb,var(--ink) 7%,transparent)}
.step button:disabled{opacity:.3;cursor:default}
.step output{min-width:34px;text-align:center;font:600 15px var(--sans);font-variant-numeric:tabular-nums}
.addrow input{flex:1;min-width:0;font:inherit;font-size:15px;color:var(--ink);background:transparent;border:0;padding:6px 0}
.addrow input::placeholder{color:var(--faint)}
.addrow input:focus{outline:none}
.why{color:var(--mute);font-size:15px;text-align:center;padding:40px 0}
.set .foot{margin-top:44px}
@media (max-width:560px){
.row{gap:10px;padding:7px 14px}
.lrow{flex-wrap:wrap;row-gap:2px}
.lrow .hb{order:9;flex-basis:100%;padding:0 0 4px 44px}
.gt{margin-top:32px}
}
"""

SETTINGS_JS = r"""<script>
(()=>{
const D=document,app=D.getElementById('app'),st=D.querySelector('.lnav output');
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const GRIP='<span class="gr" aria-hidden="true"><svg viewBox="0 0 10 16"><circle cx="2.5" cy="3" r="1.4"/><circle cx="7.5" cy="3" r="1.4"/><circle cx="2.5" cy="8" r="1.4"/><circle cx="7.5" cy="8" r="1.4"/><circle cx="2.5" cy="13" r="1.4"/><circle cx="7.5" cy="13" r="1.4"/></svg></span>';
const ORD=n=>'<span class="ord"><button type="button" data-mv="-1" aria-label="Move '+esc(n)+' up"><svg viewBox="0 0 12 12"><path d="M2 8l4-4 4 4"/></svg></button><button type="button" data-mv="1" aria-label="Move '+esc(n)+' down"><svg viewBox="0 0 12 12"><path d="M2 4l4 4 4-4"/></svg></button></span>';
const SW=(on,label,attrs)=>'<input class="sw" type="checkbox" role="switch" aria-label="'+esc(label)+'"'+(on?' checked':'')+(attrs||'')+'>';
const group=(id,title,chip,rows,note)=>'<div class="gt"><h2 id="h-'+id+'">'+title+'</h2>'+(chip?'<span class="chip">'+chip+'</span>':'')+'</div><ul class="grp" id="g-'+id+'" aria-labelledby="h-'+id+'">'+rows+'</ul>'+(note?'<p class="note">'+note+'</p>':'');
let S=null,pend=new Set(),timer=null,chain=Promise.resolve(),fade=null;
function status(msg,kind){clearTimeout(fade);st.textContent=msg;st.classList.toggle('bad',kind==='bad');st.style.opacity=1;
  if(kind==='ok')fade=setTimeout(()=>{st.style.opacity=0},2500)}
function render(){
  const src=S.sources.map(s=>'<li class="row'+(s.key==='github_prs_bs'?' ind':'')+'" data-k="'+s.key+'"><span class="sname">'+esc(s.label)
    +'<small>'+({github_prs_bs:'Off by default. Titles are redacted like everything else.',claude_sessions:'Off by default. Claude Code sessions active in the last 7 days, with an Open link. Titles are redacted; no transcript content is read.',rize:'Hours per lane from Rize, this week and last. Project names stay off the page.'}[s.key]||'Open PRs where your review is requested, and your own.')+'</small>'
    +'</span>'+SW(s.on,s.label)+'</li>').join('');
  const sec=S.sections.map(s=>'<li class="row" data-k="'+s.key+'">'+GRIP+'<span class="sname">'+esc(s.label)+(s.key==='prs'?'<small class="why-prs" hidden>Not drawn while GitHub pull requests is off.</small>':'')+'</span>'+ORD(s.label)+SW(s.visible,'Show '+s.label)+'</li>').join('');
  const lan=S.lanes.map(l=>'<li class="row lrow l-'+esc(l.key)+'" data-k="'+esc(l.key)+'">'+GRIP+'<span class="ld" aria-hidden="true"></span><input class="tx" maxlength="60" value="'+esc(l.name)+'" aria-label="Lane name" spellcheck="false">'
    +'<label class="hb"><input inputmode="decimal" value="'+(l.hours_budget==null?'':l.hours_budget)+'" placeholder="None" aria-label="Hours per week for '+esc(l.name)+'">h / week</label>'+ORD(l.name)+'</li>').join('');
  const skipL=new Set(S.reminder_skip_lists.map(s=>s.toLowerCase()));
  const lists=S.known_lists.map(n=>'<li class="row" data-n="'+esc(n)+'"><span class="sname">'+esc(n)+'</span>'+SW(!skipL.has(n.toLowerCase()),'Read '+n)+'</li>').join('');
  const skipC=new Set(S.calendar_skip);
  const cals=S.known_calendars.map(n=>'<li class="row" data-n="'+esc(n)+'"><span class="sname">'+esc(n)+'</span>'+SW(!skipC.has(n),'Read '+n)+'</li>').join('')
    +'<li class="row addrow"><input placeholder="Ignore another calendar by name" maxlength="100" aria-label="Calendar to ignore"></li>';
  app.innerHTML=group('sources','Sources','Test',src,'A source that is off makes no calls, and its section is not drawn.')
    +group('sections','Sections','',sec,'Drag, or use the arrows, to change the order of the main page.')
    +group('lanes','Lanes','',lan,'Hours per week is the budget the Hours section books calendar time against. Leave it empty for no budget.')
    +group('fresh','Freshness','','<li class="row"><span class="sname">Days before something counts as quiet<small>Lane gauges turn red, and pull requests are marked quiet, after this many days without activity.</small></span><span class="step"><button type="button" data-d="-1" aria-label="One day less">−</button><output aria-live="polite">'+S.stale_days+'</output><button type="button" data-d="1" aria-label="One day more">+</button></span></li>','')
    +group('lists','Reminder lists','',lists,'A list that is off is not read, and its reminders cannot be changed from the cockpit.')
    +group('cals','Calendars','',cals,'A calendar that is off is not read. Calendars with no events this week only appear once switched off here.');
  sync();
}
function sync(){
  const gh=app.querySelector('#g-sources [data-k="github_prs"] .sw'),bs=app.querySelector('#g-sources [data-k="github_prs_bs"]');
  if(gh&&bs){bs.querySelector('.sw').disabled=!gh.checked;bs.classList.toggle('off',!gh.checked)}
  const w=app.querySelector('.why-prs');if(w&&gh)w.hidden=gh.checked;
  app.querySelectorAll('.grp').forEach(g=>{const rows=[...g.children].filter(r=>r.querySelector('.ord'));
    rows.forEach((r,i)=>{const b=r.querySelectorAll('.ord button');b[0].disabled=i===0;b[1].disabled=i===rows.length-1})});
  const v=+app.querySelector('.step output').textContent,b=app.querySelectorAll('.step button');b[0].disabled=v<=1;b[1].disabled=v>=365;
}
const num=s=>{s=s.trim().replace(',','.');if(!s)return null;const n=Number(s);return isFinite(n)?n:s};
function read(key){
  if(key==='sources'){const o={};app.querySelectorAll('#g-sources .row').forEach(r=>o[r.dataset.k]=r.querySelector('.sw').checked);return o}
  if(key==='sections')return[...app.querySelectorAll('#g-sections .row')].map(r=>({key:r.dataset.k,visible:r.querySelector('.sw').checked}));
  if(key==='lanes')return[...app.querySelectorAll('#g-lanes .row')].map(r=>({key:r.dataset.k,name:r.querySelector('.tx').value,hours_budget:num(r.querySelector('.hb input').value)}));
  if(key==='stale_days')return+app.querySelector('.step output').textContent;
  if(key==='reminder_skip_lists')return[...app.querySelectorAll('#g-lists .row')].filter(r=>!r.querySelector('.sw').checked).map(r=>r.dataset.n);
  if(key==='calendar_skip')return[...app.querySelectorAll('#g-cals .row[data-n]')].filter(r=>!r.querySelector('.sw').checked).map(r=>r.dataset.n);
}
function queue(key,ms){pend.add(key);clearTimeout(timer);timer=setTimeout(flush,ms);window.cockpitBusy=true}
function flush(keep){clearTimeout(timer);if(!pend.size)return;const body={};pend.forEach(k=>body[k]=read(k));pend.clear();
  status('Saving…');
  chain=chain.then(()=>fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive:!!keep})
    .then(r=>r.json().catch(()=>({})).then(j=>{
      if(r.ok&&j.ok)status('Saved','ok');
      else if(r.status===503)status('Saved. The page will catch up at the next refresh.','ok');
      else status(j.error||'Could not save that change.','bad')}))
    .catch(()=>status('Could not save. The local cockpit server is not answering.','bad')));
}
addEventListener('pagehide',()=>flush(true));
const grpKey=g=>({'g-sources':'sources','g-sections':'sections','g-lanes':'lanes','g-lists':'reminder_skip_lists','g-cals':'calendar_skip'})[g.id];
app.addEventListener('change',e=>{const t=e.target;if(t.classList.contains('sw')){sync();queue(grpKey(t.closest('.grp')),400)}});
app.addEventListener('input',e=>{const t=e.target;if(t.closest('#g-lanes'))queue('lanes',700)});
app.addEventListener('click',e=>{
  const mv=e.target.closest('[data-mv]');
  if(mv){const r=mv.closest('.row'),d=+mv.dataset.mv,o=d<0?r.previousElementSibling:r.nextElementSibling;if(!o||!o.querySelector('.ord'))return;
    d<0?o.before(r):o.after(r);sync();(mv.disabled?r.querySelector('[data-mv="'+(-d)+'"]'):mv).focus();queue(grpKey(r.parentNode),400);return}
  const sd=e.target.closest('[data-d]');
  if(sd){const o=app.querySelector('.step output'),v=Math.min(365,Math.max(1,+o.textContent+ +sd.dataset.d));o.textContent=v;sync();queue('stale_days',600)}
});
app.addEventListener('keydown',e=>{const t=e.target;if(!t.closest('.addrow')||e.key!=='Enter')return;e.preventDefault();
  const n=t.value.trim();if(!n)return;t.value='';
  let r=[...app.querySelectorAll('#g-cals .row[data-n]')].find(x=>x.dataset.n===n);
  if(!r){t.closest('.addrow').insertAdjacentHTML('beforebegin','<li class="row" data-n="'+esc(n)+'"><span class="sname">'+esc(n)+'</span>'+SW(false,'Read '+n)+'</li>');queue('calendar_skip',400)}
  else if(r.querySelector('.sw').checked){r.querySelector('.sw').checked=false;queue('calendar_skip',400)}
});
let drag=null;
app.addEventListener('pointerdown',e=>{const g=e.target.closest('.gr');if(!g||e.button)return;e.preventDefault();
  const r=g.closest('.row');drag={r,id:e.pointerId,moved:false,start:[...r.parentNode.children].indexOf(r)};
  g.setPointerCapture(e.pointerId);r.classList.add('lift');D.body.classList.add('dragging')});
app.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;const r=drag.r;let p,n;
  while((p=r.previousElementSibling)&&e.clientY<p.getBoundingClientRect().top+p.offsetHeight/2)p.before(r);
  while((n=r.nextElementSibling)&&n.querySelector('.ord')&&e.clientY>n.getBoundingClientRect().top+n.offsetHeight/2)n.after(r)});
const end=e=>{if(!drag||e.pointerId!==drag.id)return;const r=drag.r,moved=[...r.parentNode.children].indexOf(r)!==drag.start;
  r.classList.remove('lift');D.body.classList.remove('dragging');drag=null;sync();if(moved)queue(grpKey(r.parentNode),400)};
app.addEventListener('pointerup',end);app.addEventListener('pointercancel',end);
fetch('/api/settings',{cache:'no-store'}).then(r=>{if(!r.ok)throw 0;return r.json()}).then(j=>{S=j;render()})
  .catch(()=>{app.innerHTML='<p class="why">Settings could not be loaded. Open this page from the cockpit at http://127.0.0.1:8765/settings.html.</p>'});
})();
</script>"""

BACK = '<a class="back" href="./"><svg viewBox="0 0 8 13" aria-hidden="true"><path d="M6.5 1.5L1.5 6.5l5 5"/></svg>Back to cockpit</a>'


def build_settings():
    body = f"""<nav class="lnav" aria-label="Settings"><div><b>Work Cockpit</b><output role="status" aria-live="polite"></output>{BACK}</div></nav>
<main class="wrap set"><header class="hero"><p>Changes save as you make them</p><h1>Settings</h1></header>
<div id="app"><p class="why">Loading</p></div>
<p class="foot">Lane mapping rules and redacted words are edited by hand in config.json.</p></main>{SETTINGS_JS}"""
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Settings · Work Cockpit</title>
<link rel="icon" href="icon.png"><link rel="apple-touch-icon" href="icon.png"><meta name="apple-mobile-web-app-title" content="Work Cockpit">
<style>{COMPONENTS}{D_CSS}{SETTINGS_CSS}</style></head><body>{body}</body></html>"""
    assert "—" not in doc
    tmp = ROOT / "out" / "settings.html.tmp"
    tmp.write_text(doc)
    tmp.replace(ROOT / "out" / "settings.html")


if LIVE:
    build_d()
    build_settings()
    print("wrote out/cockpit-d.html, out/settings.html")
else:
    build_a()
    build_b()
    build_c()
    build_d()
    print("wrote", ", ".join(str(p.relative_to(ROOT)) for p in sorted(OUT.glob("*.html"))))
