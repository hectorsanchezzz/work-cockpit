"""Weekly timetable as calendar events, from config.json (no calendar app needed).

config.json:
  "weekly_schedule": [
    {"day": "mon", "start": "08:30", "end": "12:30", "title": "IoT", "lane": "iot"},
    ...
  ]
day: mon tue wed thu fri sat sun (English or Spanish: lun mar mie jue vie sab dom).
lane: a lane key from "lanes". Returns events for the next `days` days (today included) as
{title, calendar, lane, start, end, allDay}, local naive ISO times, calendar name "Schedule".
"""
import datetime as dt

DAYS = {"mon": 0, "lun": 0, "tue": 1, "mar": 1, "wed": 2, "mie": 2, "thu": 3, "jue": 3,
        "fri": 4, "vie": 4, "sat": 5, "sab": 5, "sun": 6, "dom": 6}


def events(slots, days=7, today=None):
    today = today or dt.date.today()
    out = []
    for i in range(days):
        day = today + dt.timedelta(days=i)
        for s in slots:
            if DAYS.get(str(s.get("day", "")).lower()[:3]) != day.weekday():
                continue
            try:
                start = dt.datetime.combine(day, dt.time.fromisoformat(s["start"]))
                end = dt.datetime.combine(day, dt.time.fromisoformat(s["end"]))
            except (KeyError, ValueError):
                continue
            out.append({"title": s.get("title", ""), "calendar": "Schedule", "lane": s.get("lane"),
                        "start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
                        "allDay": False})
    return out
