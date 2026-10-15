"""Fetch + parse the Google Calendar secret iCal feed into Meeting objects."""
import re
import urllib.request
from datetime import datetime, timedelta, timezone

import icalendar
import recurring_ical_events

from .scheduler import Meeting

MEET_RE = re.compile(r"https://meet\.google\.com/[a-z0-9\-]+(?:\?[^\s\"<>]*)?", re.I)


def fetch_ics(url: str) -> bytes:
    url = url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "MeetReminder/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def _text(comp, name):
    v = comp.get(name)
    return str(v) if v is not None else ""


def _declined(comp, my_email):
    if not my_email:
        return False
    att = comp.get("ATTENDEE")
    if att is None:
        return False
    for a in (att if isinstance(att, list) else [att]):
        if str(a).lower().endswith(my_email.lower()):
            if str(a.params.get("PARTSTAT", "")).upper() == "DECLINED":
                return True
    return False


def parse_meetings(ics_bytes: bytes, now=None, hours=24, only_meet=True, my_email=""):
    now = now or datetime.now(timezone.utc)
    cal = icalendar.Calendar.from_ical(ics_bytes)
    comps = recurring_ical_events.of(cal).between(now - timedelta(hours=1),
                                                  now + timedelta(hours=hours))
    meetings = []
    for c in comps:
        start = c.decoded("DTSTART")
        if not isinstance(start, datetime):      # all-day event
            continue
        if _text(c, "STATUS").upper() == "CANCELLED" or _declined(c, my_email):
            continue
        blob = " ".join(_text(c, n) for n in
                        ("LOCATION", "DESCRIPTION", "URL", "X-GOOGLE-CONFERENCE",
                         "X-GOOGLE-HANGOUT"))
        m = MEET_RE.search(blob)
        if only_meet and not m:
            continue
        start_utc = start.astimezone(timezone.utc)  # naive -> treated as local time
        end = c.get("DTEND")
        end_utc = end.dt.astimezone(timezone.utc) if end is not None and isinstance(end.dt, datetime) \
            else start_utc + timedelta(hours=1)
        uid = _text(c, "UID") or _text(c, "SUMMARY")
        meetings.append(Meeting(
            key=f"{uid}|{start_utc.isoformat()}",
            title=_text(c, "SUMMARY") or "(No title)",
            start=start_utc, end=end_utc,
            link=m.group(0) if m else ""))
    return sorted(meetings, key=lambda x: x.start)
