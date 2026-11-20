"""Calendar from iCal (.ics) feeds, read only. Replaces Apple Calendar (ekctl) on Windows.

config.json:
  "calendar_ics": [{"name": "UAB", "url": "https://.../export_execute.php?...authtoken=..."}]
  "calendars": {"UAB": "tfg"}        # calendar name -> lane, as before
The URL often carries a secret token, so it lives only in config.json (git-ignored) and is never
printed or logged. Errors name the calendar, never the URL.

Returns events as {title, calendar, start, end, allDay} with local naive ISO times, like ekctl did.
"""
import datetime as dt
import re
import urllib.error
import urllib.request


def _unfold(text):
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _unescape(s):
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), s)


def _when(name, params, value):
    """(naive local datetime, all_day)."""
    if "VALUE=DATE" in params.upper() or re.fullmatch(r"\d{8}", value):
        return dt.datetime.strptime(value[:8], "%Y%m%d"), True
    if value.endswith("Z"):
        utc = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        return utc.astimezone().replace(tzinfo=None), False
    return dt.datetime.strptime(value[:15], "%Y%m%dT%H%M%S"), False  # floating or TZID: taken as local


def parse(text, calendar):
    events, cur = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            if "DTSTART" in cur:
                s, all_day = cur["DTSTART"]
                e = cur.get("DTEND", (s, all_day))[0]
                if all_day and e > s:  # iCal all-day end is exclusive
                    e -= dt.timedelta(days=1)
                events.append({"title": cur.get("SUMMARY", ""), "calendar": calendar,
                               "category": re.sub(r"\s*\[[^\]]*\]\s*$", "", cur.get("CATEGORIES", "")),  # Moodle: the course
                               "start": s.isoformat(timespec="seconds"), "end": e.isoformat(timespec="seconds"),
                               "allDay": all_day})
            cur = None
        elif cur is not None and ":" in line:
            head, value = line.split(":", 1)
            name, _, params = head.partition(";")
            name = name.upper()
            try:
                if name in ("DTSTART", "DTEND"):
                    cur[name] = _when(name, params, value.strip())
                elif name in ("SUMMARY", "CATEGORIES"):
                    cur[name] = _unescape(value).strip()
            except ValueError:
                pass
    return events


def fetch(feeds, days=7, past_days=1):
    """All events from the feeds that fall in [today - past_days, today + days]. Returns (events, errors)."""
    today = dt.date.today()
    lo = dt.datetime.combine(today - dt.timedelta(days=past_days), dt.time.min)
    hi = dt.datetime.combine(today + dt.timedelta(days=days + 1), dt.time.min)
    events, errors = [], []
    for f in feeds:
        name = f.get("name") or "Calendar"
        try:
            req = urllib.request.Request(f["url"], headers={"User-Agent": "work-cockpit"})
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode("utf-8", "replace")
            for e in parse(text, name):
                if lo <= dt.datetime.fromisoformat(e["start"]) < hi:
                    events.append(e)
        except urllib.error.HTTPError as ex:
            errors.append(f"Calendar ({name}): HTTP {ex.code}")
        except Exception as ex:  # never str() a request: the URL holds a token
            errors.append(f"Calendar ({name}): {type(ex).__name__}")
    return events, errors
