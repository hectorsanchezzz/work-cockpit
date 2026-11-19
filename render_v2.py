#!/usr/bin/env python3
"""Render cockpit v2 (out/cockpit-v2.html): the same data as v1, drawn visually.

Sections: summary figures, days-since-touched chart per lane and source,
this week's calendar by lane with planned hours, and lane cards with age bars.
Titles and IDs only. No em dashes.
"""
from model import *  # noqa: F401,F403
import datetime as dt
import html
import math

SOURCES = ["Linear", "Code", "Vault"]
LANE_CFG = CFG["lanes"]
NAME = {l["key"]: l["name"] for l in LANE_CFG}
SHORT = {l["key"]: l.get("short") or l["name"] for l in LANE_CFG}


def esc(s):
    return html.escape(str(s))


# ---------- scale for the staleness chart (square root, labelled ticks) ----------
ages = [age(v) for L in lanes.values() for v in L["touch"].values() if age(v) is not None]
# Axis ends at the next round value above the oldest touch (5% headroom), never below the stale line.
_need = max(ages + [STALE * 2]) * 1.05
CAP = next((c for c in (30, 60, 90, 120, 150, 180, 240, 365, 540, 730) if c >= _need), int(math.ceil(_need / 365)) * 365)
SPAN = 86
TICKS = [t for t in (0, 7, 14, 30, 60, 90, 120, 180, 240, 365, 540) if t < CAP]
TICKS = [t for t in TICKS if math.sqrt(t / CAP) < 0.92] + [CAP]  # keep labels from colliding with the end tick


def pos(days):
    # The scale stops at SPAN% so the age label after the longest bar still fits in the track.
    return SPAN * math.sqrt(max(0, min(days, CAP)) / CAP)


def touch_chart():
    axis = "".join(f'<span class="tick" style="left:{pos(t):.2f}%">{t}d</span>' for t in TICKS)
    grid = "".join(f'<i style="left:{pos(t):.2f}%"></i>' for t in TICKS)
    zone = f"--z:{pos(STALE):.2f}%"
    rows = []
    for lc in LANE_CFG:
        k = lc["key"]
        t = lanes[k]["touch"]
        bars = []
        for src in SOURCES:
            if src not in t:
                bars.append(f'<div class="bar-row"><span class="src">{src}</span><div class="track" style="{zone}">{grid}'
                            f'<span class="none">no activity found</span></div></div>')
                continue
            a = age(t[src]) or 0
            cls = "bad" if a > STALE else "ok"
            w = max(pos(a), 0.8)
            bars.append(f'<div class="bar-row"><span class="src">{src}</span><div class="track" style="{zone}">{grid}'
                        f'<span class="bar {cls}" style="width:{w:.2f}%"></span>'
                        f'<span class="val {cls}" style="left:{w:.2f}%">{fmt_age(a)}</span></div></div>')
        rows.append(f'<div class="tc-lane"><div class="tc-name"><span class="dot l-{k}"></span>{clean(SHORT.get(k, lc["name"]))}</div>'
                    f'<div class="tc-bars">{"".join(bars)}</div></div>')
    return (f'<div class="tc"><div class="tc-axis"><span></span><div class="axis-track" style="{zone}">{axis}'
            f'<span class="zone-label" style="left:{pos(STALE):.2f}%">stale after {STALE}d</span></div></div>{"".join(rows)}</div>')


# ---------- this week ----------
def parse_dt(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace(" ", "T"))
    except (ValueError, TypeError):
        return None


DAYS = [TODAY + dt.timedelta(days=i) for i in range(7)]


def week():
    head = "".join(f'<div class="wk-h {"today" if dd == TODAY else ""}">{dd.strftime("%a")}<b>{dd.day}</b></div>' for dd in DAYS)
    rows = []
    for lc in LANE_CFG:
        k = lc["key"]
        cells, hours = [], 0.0
        for dd in DAYS:
            chips = []
            for e in sorted(lanes[k]["events"], key=lambda e: e.get("start") or ""):
                s, en = parse_dt(e.get("start")), parse_dt(e.get("end"))
                if not s or s.date() != dd:
                    continue
                if e.get("allDay"):
                    when = "all day"
                else:
                    when = s.strftime("%H:%M")
                    if en and en > s:
                        hours += (en - s).total_seconds() / 3600
                chips.append(f'<div class="ev l-{k}" title="{clean(e["title"])}"><span>{when}</span>{clean(e["title"])}</div>')
            cells.append(f'<div class="wk-c">{"".join(chips)}</div>')
        budget = lc.get("hours_budget")
        if budget:
            pct = min(100, 100 * hours / budget)
            over = hours > budget
            plan = (f'<div class="plan"><b class="{"badtxt" if over else ""}">{hours:.1f}</b> / {budget} h'
                    f'<span class="meter"><span class="{"bad" if over else "ok"}" style="width:{pct:.0f}%"></span></span></div>')
        else:
            plan = f'<div class="plan"><b>{hours:.1f}</b> h booked<span class="hint">no budget set</span></div>'
        rows.append(f'<div class="wk-name"><span class="dot l-{k}"></span>{clean(SHORT.get(k, lc["name"]))}</div>{"".join(cells)}{plan}')
    return (f'<div class="scroll"><div class="wk"><div></div>{head}<div class="wk-h">Planned</div>{"".join(rows)}</div></div>')


# ---------- day by day ----------
AG_FIRST = 8  # items shown per day column before "more"
AG_OVER_FIRST = 6
ACT = False  # set by proposals.build_d on the live page: reminder cards get Done and the actions menu
AG_TODAY = []  # filled by agenda(), read by the summary for the menu bar
AG_OVER = [0]


def agenda():
    """Everything with a date, one column per day: events, reminders and Linear issues, across all lanes."""
    cols = {"over": []}
    for dd in DAYS:
        cols[dd] = []
    undated = {}
    for lc in LANE_CFG:
        k = lc["key"]
        L = lanes[k]
        for e in L["events"]:
            s = parse_dt(e.get("start"))
            if not s or s.date() not in cols:
                continue
            when = "all day" if e.get("allDay") else s.strftime("%H:%M")
            cols[s.date()].append({"lane": k, "kind": "ev", "sort": "0" if e.get("allDay") else when,
                                   "when": when, "title": e["title"], "id": "", "url": None})
        for r in L["reminders"]:
            due = d(r.get("due"))
            if not due:
                undated[k] = undated.get(k, 0) + 1
                continue
            tm = str(r["due"])[11:16]
            it = {"lane": k, "kind": "rem", "sort": tm or "99", "when": tm, "title": r["title"], "id": "",
                  "url": None, "recurring": r.get("recurring"), "due": due, "rid": r.get("id")}
            if due < TODAY:
                cols["over"].append(it)
            elif due in cols:
                cols[due].append(it)
        for i in L["started"] + L["todo"]:
            due = d(i.get("due"))
            if not due:
                continue
            it = {"lane": k, "kind": "lin", "sort": "98", "when": "", "title": i["title"], "id": i["id"],
                  "url": i["url"], "due": due}
            if due < TODAY:
                cols["over"].append(it)
            elif due in cols:
                cols[due].append(it)

    AG_TODAY[:] = sorted(cols.get(TODAY, []), key=lambda i: i["sort"])
    AG_OVER[0] = len(cols["over"])

    def chip(it, late=False):
        k = it["lane"]
        if it["kind"] == "ev":
            lead = f'<span class="ag-t">{clean(it["when"])}</span>'
        elif it["kind"] == "rem" and ACT and it.get("rid"):
            lead = (f'<button class="ck" type="button" aria-label="Mark done: {clean(it["title"])}"><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="5.25"/><path d="M3.6 6.1l1.6 1.6 3.2-3.3"/></svg></button>'
                    + (f'<span class="ag-t">{clean(it["when"])}</span>' if it["when"] else ""))
        elif it["kind"] == "rem":
            lead = '<span class="ag-ico rem" aria-label="Reminder"></span>' + (f'<span class="ag-t">{clean(it["when"])}</span>' if it["when"] else "")
        else:
            lead = f'<span class="ag-ico lin" aria-label="Linear"></span><span class="id">{clean(it["id"])}</span>'
        tail = ""
        if late:
            tail = f'<span class="ag-late">{(TODAY - it["due"]).days}d late</span>'
        if it.get("recurring"):
            tail += '<span class="ag-rec" title="Repeats">repeats</span>'
        body = f'{lead}<span class="t">{clean(it["title"])}</span>{tail}'
        if it["url"]:
            body = f'<a href="{esc(it["url"])}" target="_blank" rel="noopener">{body}</a>'
        attrs = ""
        if it["kind"] == "rem" and ACT and it.get("rid"):  # the card opens the same actions menu as the rows above
            attrs = (f' data-rid="{esc(it["rid"])}" data-due="{it["due"].isoformat()}" data-when="{esc(it["when"])}"'
                     ' tabindex="0" role="button" aria-haspopup="menu" aria-expanded="false"')
            if it.get("recurring"):
                attrs += ' data-rec="1"'
            if clean(it["title"]) != esc(it["title"]):
                attrs += " data-norename"
        return f'<li class="ag-i l-{k} k-{it["kind"]}" data-lane="{k}"{attrs}>{body}</li>'

    def column(key, label, sub, items, late=False):
        cls = "over" if late else ("today" if key == TODAY else "")
        n = len(items)
        cnt = f'<span class="ag-n">{n}</span>' if n else ""
        if not items:
            inner = '<p class="empty">Nothing</p>'
        else:
            n_first = AG_OVER_FIRST if late else AG_FIRST
            head = "".join(chip(i, late) for i in items[:n_first])
            rest = items[n_first:]
            tail = (f'<details><summary>{len(rest)} more</summary><ul>{"".join(chip(i, late) for i in rest)}</ul></details>' if rest else "")
            inner = f"<ul>{head}</ul>{tail}"
        return f'<div class="ag-col {cls}" data-day="{"over" if late else key.isoformat()}"><div class="ag-h">{label}<b>{sub}</b>{cnt}</div>{inner}</div>'

    over = sorted(cols["over"], key=lambda i: (i["due"], i["lane"]), reverse=True)  # most recently missed first
    out = [column("over", "Overdue", "carried", over, late=True)]
    for dd in DAYS:
        items = sorted(cols[dd], key=lambda i: (i["sort"], i["lane"]))
        label = "Today" if dd == TODAY else dd.strftime("%a")
        out.append(column(dd, label, str(dd.day), items))
    und = "".join(f'<span class="ag-ul"><span class="dot l-{k}"></span>{clean(SHORT.get(k, NAME[k]))} {n}</span>'
                  for k, n in undated.items() if n)
    legend = ('<div class="ag-legend"><span><span class="ag-t">09:00</span>event</span>'
              '<span><span class="ag-ico rem"></span>reminder</span><span><span class="ag-ico lin"></span>Linear issue due</span>'
              + (f'<span class="ag-und">Reminders with no date: {und}</span>' if und else "") + "</div>")
    return f'{legend}<div class="ag">{"".join(out)}</div>'


# ---------- lane cards ----------
WCAP = 60


def age_row(idtxt, title, url, days, label, kind):
    cls = "bad" if days > STALE else "ok"
    w = 100 * min(days, WCAP) / WCAP
    idh = f'<span class="id">{clean(idtxt)}</span>' if idtxt else ""
    inner = f'{idh}<span class="t">{clean(title)}</span>'
    if url:
        inner = f'<a href="{esc(url)}" target="_blank" rel="noopener">{inner}</a>'
    return (f'<li class="ar"><div class="ar-top">{inner}</div><div class="ar-bot"><span class="mini"><span class="{cls}" style="width:{w:.0f}%"></span></span>'
            f'<span class="meta {cls}">{clean(kind)} · {clean(label)}</span></div></li>')


def more(items, render, first):
    head = "".join(render(i) for i in items[:first])
    rest = items[first:]
    tail = (f'<details><summary>{len(rest)} more</summary><ul>{"".join(render(i) for i in rest)}</ul></details>' if rest else "")
    return f"<ul>{head}</ul>{tail}"


def card(lc):
    k = lc["key"]
    L = lanes[k]
    t = L["touch"]
    last = max(t.values()) if t else None
    la = age(last)
    stale_src = [s for s, v in t.items() if (age(v) or 0) > STALE]
    if la is None or la > STALE:
        pill = f'<span class="pill bad">Quiet {fmt_age(la)}</span>'
    elif stale_src:
        pill = f'<span class="pill warn">{", ".join(stale_src)} quiet</span>'
    else:
        pill = f'<span class="pill ok">Active {fmt_age(la)}</span>'

    waiting = sorted(L["waiting"], key=lambda i: i.get("date") or "")
    wait_html = more(waiting, lambda i: age_row(i["id"], i["title"], i["url"], age(i["date"]) or 0,
                                               f'{fmt_age(age(i["date"]))}', i["kind"]), 4) if waiting else '<p class="empty">Nothing waiting on you</p>'
    over = sorted(L["overdue"], key=lambda i: i.get("due") or "")
    over_html = more(over, lambda i: age_row(i["id"] if i["kind"] == "Linear" else "", i["title"], i["url"],
                                            age(i["due"]) or 0, f'{age(i["due"])}d late', i["kind"]), 4) if over else '<p class="empty">Nothing overdue</p>'
    na = next_actions(L)
    if na:
        na_html = "<ol class='na'>" + "".join(
            f'<li>{"<a href=" + chr(34) + esc(i["url"]) + chr(34) + " target=_blank rel=noopener>" if i["url"] else ""}'
            f'{"<span class=id>" + clean(i["id"]) + "</span>" if i["id"] else ""}<span class="t">{clean(i["title"])}</span>'
            f'{"</a>" if i["url"] else ""}<span class="meta">{clean(i["src"])}{" · " + clean(i["meta"]) if i["meta"] else ""}</span></li>'
            for i in na) + "</ol>"
    else:
        na_html = '<p class="empty">No open items</p>'
    stats = [("Waiting", len(L["waiting"]), ""), ("Overdue", len(L["overdue"]), "badtxt" if L["overdue"] else ""),
             ("Linear open", len(L["started"]) + len(L["todo"]), ""), ("Reminders", len(L["reminders"]), "")]
    stat_html = "".join(f'<div class="st"><b class="{c}">{n}</b><span>{lbl}</span></div>' for lbl, n, c in stats)
    return f"""<section class="card l-{k}">
  <header><h2><span class="dot l-{k}"></span>{clean(lc['name'])}</h2>{pill}</header>
  <div class="stats">{stat_html}</div>
  <h3>Next 3</h3>{na_html}
  <h3>Waiting on me <span class="h3n">oldest first</span></h3>{wait_html}
  <h3>Overdue <span class="h3n">most late first</span></h3>{over_html}
</section>"""


tot_wait = sum(len(L["waiting"]) for L in lanes.values())
tot_over = sum(len(L["overdue"]) for L in lanes.values())
quiet_n = sum(1 for L in lanes.values() if any((age(v) or 0) > STALE for v in L["touch"].values()) or not L["touch"])
oldest_wait = max([age(i["date"]) or 0 for L in lanes.values() for i in L["waiting"]] or [0])
gen_local = LOCAL.get("generated", "")[:16].replace("T", " ")
gen_lin = LIN.get("generated", "")[:16].replace("T", " ")
err_html = ""
if LOCAL.get("errors"):
    err_html = '<div class="errors">Source errors: ' + "; ".join(clean(e) for e in LOCAL["errors"]) + "</div>"

CSS = """
/* Layout: summary figures, then day-by-day agenda, staleness chart, hours by lane, then a grid of lane cards. */
:root{
--bg:#f3f4f7;--panel:#ffffff;--ink:#16181d;--mute:#5f6571;--line:#dfe2e8;--soft:#eceef3;--accent:#3550c4;
--bad:#c4372c;--badbg:#fbe8e5;--warn:#a8650c;--warnbg:#fbf0dc;--ok:#2d7a52;--okbg:#e3f2e9;--zone:rgba(196,55,44,.07);
--axis:#4c63d2;--bs:#5b6170;--delvion:#11807f;--pbe:#a8417f;--tfg:#b8740f;--personal:#4b8436;
--sans:"IBM Plex Sans",system-ui,-apple-system,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#111317;--panel:#1a1d22;--ink:#e7e8ea;--mute:#9aa0aa;--line:#2b2f36;--soft:#23272e;--accent:#8ea2ff;
--bad:#ff7b6b;--badbg:#3a1d1a;--warn:#f0b35a;--warnbg:#36290f;--ok:#6fcf97;--okbg:#16301f;--zone:rgba(255,123,107,.08);
--axis:#8a9bff;--bs:#a3a9b6;--delvion:#4cc7c4;--pbe:#e383bf;--tfg:#f0ae4b;--personal:#8fcf72;color-scheme:dark}}
:root[data-theme="dark"]{
--bg:#111317;--panel:#1a1d22;--ink:#e7e8ea;--mute:#9aa0aa;--line:#2b2f36;--soft:#23272e;--accent:#8ea2ff;
--bad:#ff7b6b;--badbg:#3a1d1a;--warn:#f0b35a;--warnbg:#36290f;--ok:#6fcf97;--okbg:#16301f;--zone:rgba(255,123,107,.08);
--axis:#8a9bff;--bs:#a3a9b6;--delvion:#4cc7c4;--pbe:#e383bf;--tfg:#f0ae4b;--personal:#8fcf72;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 var(--sans);
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px 48px}
.wrap{max-width:1360px;margin:0 auto;display:flex;flex-direction:column;gap:16px}
.l-axis{--lc:var(--axis)}.l-bs{--lc:var(--bs)}.l-delvion{--lc:var(--delvion)}.l-pbe{--lc:var(--pbe)}.l-tfg{--lc:var(--tfg)}.l-personal{--lc:var(--personal)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--lc);display:inline-block;flex:none}
.top{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:12px}
h1{font-size:22px;margin:0;letter-spacing:-.01em;text-wrap:balance}
h1 small{font:500 11px var(--mono);color:var(--mute);border:1px solid var(--line);border-radius:4px;padding:1px 5px;margin-left:8px;vertical-align:middle}
.sub{color:var(--mute);font-size:12px;margin-top:2px}
.figs{display:flex;flex-wrap:wrap;gap:10px}
.fig{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 14px;min-width:120px}
.fig b{display:block;font-size:24px;line-height:1.1;font-variant-numeric:tabular-nums}
.fig span{font-size:11.5px;color:var(--mute)}
.fig.bad b{color:var(--bad)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:0}
.panel>h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:0 0 10px;font-weight:600}
.panel>h2 em{font-style:normal;text-transform:none;letter-spacing:0;font-weight:400;margin-left:6px}
.errors{padding:8px 12px;border-radius:8px;background:var(--badbg);color:var(--bad);font-size:13px}
/* staleness chart */
.tc{display:flex;flex-direction:column;gap:10px}
.tc-axis,.tc-lane{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px;align-items:start}
.axis-track{position:relative;height:30px;margin-left:58px}
.tick{position:absolute;bottom:0;transform:translateX(-50%);font:11px var(--mono);color:var(--mute);font-variant-numeric:tabular-nums}
.tick:first-child{transform:none}
.zone-label{position:absolute;top:0;font-size:11px;color:var(--bad);padding-left:4px;white-space:nowrap}
.tc-name{display:flex;align-items:center;gap:7px;font-weight:600;font-size:13px;padding-top:2px}
.tc-bars{display:flex;flex-direction:column;gap:3px;min-width:0}
.bar-row{display:grid;grid-template-columns:50px minmax(0,1fr);gap:8px;align-items:center}
.src{font-size:11px;color:var(--mute)}
.track{position:relative;height:14px;border-radius:3px;background:linear-gradient(90deg,transparent var(--z),var(--zone) var(--z))}
.track i{position:absolute;top:0;bottom:0;width:1px;background:var(--line)}
.track .bar{position:absolute;left:0;top:3px;height:8px;border-radius:2px}
.bar.ok{background:var(--ok)}.bar.bad{background:var(--bad)}
.track .val{position:absolute;top:-1px;padding-left:6px;font:11px var(--mono);white-space:nowrap;font-variant-numeric:tabular-nums}
.val.ok{color:var(--ok)}.val.bad{color:var(--bad)}
.none{position:absolute;left:4px;top:0;font-size:11px;color:var(--mute);font-style:italic}
/* day by day */
.ag-legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:11.5px;color:var(--mute);margin:-2px 0 10px;align-items:center}
.ag-legend>span{display:inline-flex;align-items:center;gap:5px}
.ag-und{margin-left:auto;flex-wrap:wrap;gap:4px 10px!important}
.ag-ul{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
.ag{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:8px}
.ag-col{background:var(--soft);border-radius:8px;padding:8px;min-width:0;display:flex;flex-direction:column;gap:6px}
.ag-col.today{background:var(--panel);box-shadow:inset 0 0 0 2px var(--accent)}
.ag-col.over{background:var(--badbg)}
.ag-h{font-size:11px;color:var(--mute);text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:baseline;gap:5px}
.ag-h b{font-size:15px;color:var(--ink);letter-spacing:0;font-variant-numeric:tabular-nums}
.ag-col.today .ag-h b,.ag-col.today .ag-h{color:var(--accent)}
.ag-col.over .ag-h,.ag-col.over .ag-h b{color:var(--bad)}
.ag-col.over .ag-h b{font-size:12px;text-transform:none;font-weight:400}
.ag-n{margin-left:auto;font:600 11px var(--mono);color:var(--mute)}
.ag-col ul{display:flex;flex-direction:column;gap:4px}
.ag-i{background:var(--panel);border-left:3px solid var(--lc);border-radius:4px;padding:4px 6px;font-size:12px;line-height:1.3}
.ag-col.today .ag-i{background:var(--soft)}
.ag-i>a,.ag-i{overflow-wrap:anywhere}
.ag-i .id{font-size:10.5px;margin-right:4px}
.ag-t{font:10.5px var(--mono);color:var(--mute);margin-right:4px}
.ag-ico{display:inline-block;width:9px;height:9px;margin-right:5px;vertical-align:-1px;flex:none}
.ag-ico.rem{border:1.5px solid var(--lc,var(--mute));border-radius:50%}
.ag-ico.lin{border:1.5px solid var(--lc,var(--mute));border-radius:2px;transform:rotate(45deg) scale(.85)}
.ag-legend .ag-ico{--lc:var(--mute)}
.ag-late{display:block;font-size:10.5px;color:var(--bad);margin-top:1px}
.ag-rec{display:inline-block;font-size:10px;color:var(--mute);border:1px solid var(--line);border-radius:3px;padding:0 3px;margin-left:4px}
.ag-col details summary{font-size:11.5px}
@media (max-width:1100px){.ag{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media (max-width:640px){.ag{grid-template-columns:1fr}.ag-und{margin-left:0}}
/* week */
.scroll{overflow-x:auto}
.wk{display:grid;grid-template-columns:96px repeat(7,minmax(96px,1fr)) 120px;min-width:900px;border-top:1px solid var(--line)}
.wk>div{border-bottom:1px solid var(--line);padding:6px;min-width:0}
.wk-h{font-size:11px;color:var(--mute);text-transform:uppercase;letter-spacing:.05em}
.wk-h b{display:block;font-size:15px;color:var(--ink);letter-spacing:0;font-variant-numeric:tabular-nums}
.wk-h.today b{color:var(--accent)}
.wk-name{display:flex;align-items:center;gap:7px;font-weight:600;font-size:12.5px}
.wk-c{display:flex;flex-direction:column;gap:3px}
.ev{font-size:11.5px;line-height:1.3;padding:3px 6px;border-radius:4px;background:var(--soft);border-left:3px solid var(--lc);overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.ev span{font-family:var(--mono);color:var(--mute);margin-right:4px;font-size:10.5px}
.plan{font-size:12px;color:var(--mute);display:flex;flex-direction:column;gap:3px}
.plan b{color:var(--ink);font-size:14px;font-variant-numeric:tabular-nums}
.hint{font-size:11px}
.meter{display:block;height:6px;border-radius:3px;background:var(--soft);overflow:hidden}
.meter span{display:block;height:100%}.meter .ok{background:var(--ok)}.meter .bad{background:var(--bad)}
/* cards */
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(min(100%,380px),1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--lc);border-radius:10px;padding:12px 16px 14px;min-width:0}
.card header{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.card h2{font-size:16px;margin:0;display:flex;align-items:center;gap:8px}
.pill{font-size:11.5px;padding:2px 9px;border-radius:999px;font-weight:600;white-space:nowrap}
.pill.ok{background:var(--okbg);color:var(--ok)}.pill.bad{background:var(--badbg);color:var(--bad)}.pill.warn{background:var(--warnbg);color:var(--warn)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:10px 0 2px}
.st{background:var(--soft);border-radius:6px;padding:5px 8px}
.st b{display:block;font-size:17px;font-variant-numeric:tabular-nums}.st span{font-size:11px;color:var(--mute)}
.badtxt{color:var(--bad)!important}
h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:14px 0 4px}
.h3n{text-transform:none;letter-spacing:0;font-weight:400;margin-left:4px}
ul,ol{list-style:none;margin:0;padding:0}
.na{counter-reset:n}
.na li{counter-increment:n;position:relative;padding:4px 0 4px 22px;display:flex;flex-direction:column;border-top:1px dashed var(--line)}
.na li:first-child{border-top:0}
.na li::before{content:counter(n);position:absolute;left:0;top:5px;width:16px;height:16px;border-radius:50%;background:var(--lc);color:var(--panel);font:600 10px/16px var(--mono);text-align:center}
.ar{padding:5px 0;border-top:1px dashed var(--line)}
.ar:first-child{border-top:0}
.ar-bot{display:grid;grid-template-columns:72px 1fr;gap:8px;align-items:center;margin-top:2px}
.mini{display:block;height:5px;border-radius:3px;background:var(--soft);overflow:hidden}
.mini span{display:block;height:100%}.mini .ok{background:var(--ok)}.mini .bad{background:var(--bad)}
a{color:inherit;text-decoration:none}a:hover .t{color:var(--accent);text-decoration:underline}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
.id{font-family:var(--mono);font-size:11.5px;color:var(--accent);margin-right:6px}
.t{overflow-wrap:anywhere}
.meta{font-size:11.5px;color:var(--mute)}.meta.bad{color:var(--bad)}
.empty{color:var(--mute);font-size:12.5px;margin:2px 0}
details summary{cursor:pointer;color:var(--accent);font-size:12px;padding:4px 0}
footer{color:var(--mute);font-size:12px}
@media (max-width:560px){.tc-axis,.tc-lane{grid-template-columns:1fr}.tc-axis>span{display:none}.axis-track{margin-left:58px}.stats{grid-template-columns:repeat(2,1fr)}}
"""

page = f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Work Cockpit v2</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
<div class="wrap">
<div class="top">
  <div><h1>Work Cockpit<small>v2</small></h1>
  <div class="sub">Snapshot {clean(gen_local)} · Linear {clean(gen_lin)} · stale after {STALE} days</div></div>
  <div class="figs">
    <div class="fig"><b>{tot_wait}</b><span>waiting on me</span></div>
    <div class="fig {'bad' if tot_over else ''}"><b>{tot_over}</b><span>overdue</span></div>
    <div class="fig {'bad' if quiet_n else ''}"><b>{quiet_n}<small style="font-size:13px;color:var(--mute)"> / {len(LANE_CFG)}</small></b><span>lanes with a quiet source</span></div>
    <div class="fig"><b>{oldest_wait}d</b><span>oldest item waiting</span></div>
  </div>
</div>
{err_html}
<section class="panel"><h2>Day by day<em>everything dated: events, reminders and Linear due dates, all lanes</em></h2>{agenda()}</section>
<section class="panel"><h2>Days since last touched<em>per lane and source, square-root scale</em></h2>{touch_chart()}</section>
<section class="panel"><h2>Hours by lane<em>next 7 days of calendar, booked against budget</em></h2>{week()}</section>
<div class="grid">{''.join(card(lc) for lc in LANE_CFG)}</div>
<footer>Read-only snapshot of Linear, Apple Reminders and Calendar, GitHub, the git repos under ~/development and the vault git log. Titles and IDs only. Lane mapping and hours budgets live in ~/development/cockpit/config.json. v1 stays at its own link.</footer>
</div>
"""
assert "—" not in page
(ROOT / "out").mkdir(exist_ok=True)
(ROOT / "out" / "cockpit-v2.html").write_text(page)
print("wrote out/cockpit-v2.html", len(page), "bytes")

# Small summary for the menu bar counter (counts, titles of today's items, no details).
summary = {
    "generated": LOCAL.get("generated", ""),
    "linear_generated": LIN.get("generated", ""),
    "edited": LOCAL.get("edited", ""),
    "waiting": tot_wait, "overdue": tot_over, "quiet": quiet_n, "lanes_total": len(LANE_CFG),
    "dated_overdue": AG_OVER[0],
    "errors": len(LOCAL.get("errors") or []),
    "lanes": [{"name": lc["name"], "waiting": len(lanes[lc["key"]]["waiting"]),
               "overdue": len(lanes[lc["key"]]["overdue"]),
               "quiet": any((age(v) or 0) > STALE for v in lanes[lc["key"]]["touch"].values()) or not lanes[lc["key"]]["touch"]}
              for lc in LANE_CFG],
    "today": [{"when": i["when"] or ("due" if i["kind"] == "lin" else ""), "kind": i["kind"],
               "title": html.unescape(clean((i["id"] + " " if i["id"] else "") + str(i["title"])))} for i in AG_TODAY],
}
(ROOT / "out" / "summary.json").write_text(json.dumps(summary, ensure_ascii=False))

