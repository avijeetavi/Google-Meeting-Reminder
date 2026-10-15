"""OPTIONAL, TEMPORARY calendar source: Chrome's Google Calendar pop-ups (Windows toast notifications).

Use it only until you get a Google OAuth client from IT (see gcal_api.py / GOOGLE_API_SETUP.md); then delete this
file and run `python meet_reminder.py --source=api`.

How it works: Windows keeps toast notifications in a small SQLite database
(%LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db). When Google Calendar in Chrome fires its
"meeting soon" pop-up, we read that entry, work out the meeting's start time, and let the normal plane reminder
take over (every minute until 5 min after the start). Nothing is sent anywhere.

PRIVACY: that database also holds notifications from other apps/sites. This module
  * opens it READ-ONLY (never copies or changes it),
  * looks only at rows from Chrome/Edge and keeps only those that mention calendar.google.com,
  * discards everything else immediately, and never logs, prints or stores non-Calendar content.
  (`probe()` prints, for other Chrome notifications, only the site name - never their text.)

LIMITS (read before relying on it):
  * It learns about a meeting only when Google's own pop-up fires (default: 10 min before). Meetings with
    no pop-up (reminders removed), or a pop-up you dismissed before this app saw it, are missed.
  * The pop-up text format is not documented by Google; the start time is parsed from it ("in 10 minutes",
    "10:30 - 11:00 AM", "now") and falls back to arrival + `default_lead` minutes. Run `--probe-notifications`
    with a real pop-up to check what it sees.
  * The Windows database layout is undocumented and may differ by Windows build; unexpected layouts raise a
    clear error instead of guessing. Security software may flag this access - if so, stop and ask IT.
"""
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .scheduler import Meeting

MEET_RE = re.compile(r"https://meet\.google\.com/[a-z0-9\-]+(?:\?[^\s\"<>]*)?", re.I)
BROWSERS = ("chrome", "msedge", "edge")
FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def default_db_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Notifications" / "wpndatabase.db"


def _arrival(v, fallback):
    """Notification.ArrivalTime is normally a Windows FILETIME (100 ns ticks since 1601)."""
    try:
        d = FILETIME_EPOCH + timedelta(microseconds=int(v) / 10)
        return d if 2000 <= d.year <= 2100 else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


# ------------------------------------------------------------------ parsing (pure, testable)
def parse_toast(payload) -> dict:
    """Toast XML (bytes or str) -> {'texts': [...], 'attribution': str, 'launch': str, 'args': [...]}."""
    if isinstance(payload, (bytes, bytearray)):
        for enc in ("utf-8", "utf-16"):
            try:
                payload = bytes(payload).decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("undecodable toast payload")
    root = ET.fromstring(payload.strip("\x00﻿ \r\n\t"))
    texts, attribution = [], ""
    for t in root.iter("text"):
        val = "".join(t.itertext()).strip()
        if not val:
            continue
        if t.get("placement") == "attribution":
            attribution = val
        else:
            texts.append(val)
    return {"texts": texts, "attribution": attribution, "launch": root.get("launch", ""),
            "args": [a.get("arguments", "") for a in root.iter("action")]}


def is_calendar(p: dict) -> bool:
    return "calendar.google.com" in " ".join([p["attribution"], p["launch"], *p["args"], *p["texts"]]).lower()


_REL_MIN = re.compile(r"\bin\s+(\d+)\s*(?:min|minute)s?\b", re.I)
_REL_HR = re.compile(r"\bin\s+(\d+)\s*(?:hour|hr)s?(?:\s+(?:and\s+)?(\d+)\s*(?:min|minute)s?)?\b", re.I)
_NOW = re.compile(r"\b(?:now|starting|started)\b", re.I)
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\s*([ap])\.?m\.?|\b(\d{1,2}):(\d{2})\b|\b(\d{1,2})\s*([ap])\.?m\.?", re.I)


def _clock_minutes(h, m, ap):
    h = int(h) % 12 + (12 if ap and ap.lower() == "p" else 0) if ap else int(h)
    return h * 60 + int(m or 0)


def _times(text):
    """All clock times in `text` as (minutes_since_midnight, had_ampm, ampm)."""
    out = []
    for m in _CLOCK.finditer(text):
        if m.group(1):
            out.append((int(m.group(1)), int(m.group(2)), m.group(3)))
        elif m.group(4):
            out.append((int(m.group(4)), int(m.group(5)), None))
        else:
            out.append((int(m.group(6)), 0, m.group(7)))
    return out


def guess_start(body: str, arrival: datetime, default_lead: int) -> datetime:
    """Meeting start (UTC) from the pop-up body text; falls back to arrival + default_lead minutes."""
    m = _REL_HR.search(body)
    if m:
        return arrival + timedelta(hours=int(m.group(1)), minutes=int(m.group(2) or 0))
    m = _REL_MIN.search(body)
    if m:
        return arrival + timedelta(minutes=int(m.group(1)))
    ts = _times(body)
    if ts:
        h, mi, ap = ts[0]
        if ap is None and len(ts) > 1 and ts[1][2]:               # "11:30 - 12:00pm": borrow the suffix
            ap2 = ts[1][2].lower()
            second = _clock_minutes(ts[1][0], ts[1][1], ts[1][2])
            for cand in (ap2, "a" if ap2 == "p" else "p"):
                if _clock_minutes(h, mi, cand) <= second:
                    ap = cand
                    break
        base = arrival.astimezone()
        mins = _clock_minutes(h, mi, ap)
        start = base.replace(hour=mins // 60 % 24, minute=mins % 60, second=0, microsecond=0)
        if start < base - timedelta(hours=1):
            start += timedelta(days=1)
        return start.astimezone(timezone.utc)
    if _NOW.search(body):
        return arrival
    return arrival + timedelta(minutes=default_lead)


def to_meeting(p: dict, arrival: datetime, default_lead: int = 10) -> Meeting:
    title = p["texts"][0] if p["texts"] else "(Calendar event)"
    body = " ".join(p["texts"][1:])
    start = guess_start(body, arrival, default_lead).replace(second=0, microsecond=0)
    blob = " ".join([p["launch"], *p["args"], *p["texts"]])
    m = MEET_RE.search(blob)
    link = m.group(0) if m else (p["launch"] if p["launch"].startswith("http") else "")
    return Meeting(key=f"notif|{title}|{start.isoformat()}", title=title, start=start,
                   end=start + timedelta(minutes=30), link=link)


# ------------------------------------------------------------------ reading the Windows database
def _rows(db_path=None):
    path = Path(db_path) if db_path else default_db_path()
    if not path.exists():
        raise FileNotFoundError(f"Windows notification database not found: {path}")
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)   # read-only, no copy
    try:
        n = {r[1] for r in con.execute("PRAGMA table_info(Notification)")}
        h = {r[1] for r in con.execute("PRAGMA table_info(NotificationHandler)")}
        if not ({"HandlerId", "Payload", "ArrivalTime"} <= n and {"RecordId", "PrimaryId"} <= h):
            raise RuntimeError("unexpected Windows notification database layout (this Windows build differs); "
                               "not guessing - use the Google API instead")
        return con.execute("SELECT h.PrimaryId, n.Payload, n.ArrivalTime FROM Notification n "
                           "JOIN NotificationHandler h ON n.HandlerId = h.RecordId "
                           "ORDER BY n.ArrivalTime DESC LIMIT 400").fetchall()
    finally:
        con.close()


def calendar_notifications(db_path=None, now=None, max_age_hours=3):
    """[(parsed_toast, arrival_utc)] for Chrome/Edge notifications that come from calendar.google.com."""
    now = now or datetime.now(timezone.utc)
    out = []
    for pid, payload, arrival in _rows(db_path):
        if not any(b in str(pid).lower() for b in BROWSERS):
            continue                                                       # other apps: never touched
        when = _arrival(arrival, now)
        if now - when > timedelta(hours=max_age_hours):
            continue
        try:
            p = parse_toast(payload)
        except (ET.ParseError, ValueError):
            continue
        if is_calendar(p):                                                 # everything else is dropped here
            out.append((p, when))
    return out


class NotificationSource:
    """Same shape as the other sources: poll() -> list[Meeting]."""

    def __init__(self, default_lead=10, db_path=None, max_age_hours=3):
        self.default_lead, self.db_path, self.max_age_hours = default_lead, db_path, max_age_hours

    def poll(self, now=None):
        """Meetings learned from Calendar pop-ups. Remembered in memory until they are over, so dismissing
        or clearing the Windows pop-up does NOT stop the reminders."""
        now = now or datetime.now(timezone.utc)
        found = [to_meeting(p, when, self.default_lead)
                 for p, when in calendar_notifications(self.db_path, now, self.max_age_hours)]
        found.sort(key=lambda m: m.start)
        known = getattr(self, "_known", [])
        known = [m for m in known if (now - m.start).total_seconds() < 900]      # drop long-finished ones
        for m in found:
            if not any(x.title == m.title and abs((x.start - m.start).total_seconds()) <= 150 for x in known):
                if (now - m.start).total_seconds() < 900:
                    known.append(m)
        self._known = known
        return list(known)


def probe(db_path=None, default_lead=10):
    """Console helper: shows what the app can see. Prints Calendar pop-ups in full, other Chrome pop-ups
    only as a site name (never their text)."""
    now = datetime.now(timezone.utc)
    cal, others = 0, {}
    rows = _rows(db_path)
    apps = {}
    for pid, _, _ in rows:                       # app ids only, never any notification text
        apps[str(pid)] = apps.get(str(pid), 0) + 1
    print(f"Notification database readable: {len(rows)} stored notification(s). Apps (name: count):")
    for k, v in sorted(apps.items(), key=lambda kv: -kv[1]):
        print(f"   {k}: {v}")
    print()
    for pid, payload, arrival in rows:
        if not any(b in str(pid).lower() for b in BROWSERS):
            continue
        try:
            p = parse_toast(payload)
        except (ET.ParseError, ValueError):
            others["(unreadable)"] = others.get("(unreadable)", 0) + 1
            continue
        if is_calendar(p):
            cal += 1
            when = _arrival(arrival, now)
            m = to_meeting(p, when, default_lead)
            print(f"Calendar pop-up arrived {when.astimezone():%H:%M:%S}  texts={p['texts']}  "
                  f"attribution={p['attribution']!r}\n   -> start {m.start.astimezone():%H:%M}  link={m.link or '(none)'}")
        else:
            site = p["attribution"] or "(no site label)"
            others[site] = others.get(site, 0) + 1
    print(f"\n{cal} Google Calendar pop-up(s) found.")
    if others:
        print("Other Chrome/Edge notifications (site names only):", others)
    if not cal:
        print("None found. Trigger a Calendar reminder (or wait for one), then run this again within a few minutes.")
