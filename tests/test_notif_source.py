import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # project root
"""Headless tests for notif_source (synthetic toasts + a stand-in SQLite DB that follows the ASSUMED Windows
schema; the real wpndatabase.db layout has not been verified on the owner's machine)."""
import sqlite3, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from meetreminder import notif_source as ns

def toast(title, body, site="calendar.google.com", launch="https://calendar.google.com/calendar/event?eid=abc"):
    return (f'<toast launch="{launch}"><visual><binding template="ToastGeneric"><text>{title}</text>'
            f'<text>{body}</text><text placement="attribution">{site}</text></binding></visual>'
            f'<actions><action content="Join" arguments="https://meet.google.com/abc-defg-hij"/></actions></toast>').encode()

NOW = datetime(2026, 10, 13, 9, 50, tzinfo=timezone.utc)

# 1. parsing / classification
p = ns.parse_toast(toast("Standup", "Starts in 10 minutes"))
assert p["texts"] == ["Standup", "Starts in 10 minutes"] and p["attribution"] == "calendar.google.com"
assert ns.is_calendar(p) and not ns.is_calendar(ns.parse_toast(toast("Hi", "x", site="slack.com", launch="https://slack.com/x")))
assert ns.parse_toast(toast("A", "B").decode().encode("utf-16"))["texts"] == ["A", "B"]      # UTF-16 payloads too

# 2. start-time guesses
g = lambda body, lead=10: ns.guess_start(body, NOW, lead)
assert g("Starts in 10 minutes") == NOW + timedelta(minutes=10)
assert g("in 1 minute") == NOW + timedelta(minutes=1)
assert g("In 1 hour 30 minutes") == NOW + timedelta(minutes=90)
assert g("Starting now") == NOW
assert g("something unrecognisable") == NOW + timedelta(minutes=10)
assert g("something unrecognisable", lead=15) == NOW + timedelta(minutes=15)
loc = NOW.astimezone()
for body, hh, mm in (("10:30 – 11:00 AM", 10, 30), ("11:30 – 12:00pm", 11, 30), ("2:15pm – 3pm", 14, 15),
                     ("14:05", 14, 5), ("9 AM", 9, 0)):
    st = ns.guess_start(body, NOW, 10).astimezone()
    assert (st.hour, st.minute) == (hh, mm), (body, st)
    assert st >= loc - timedelta(hours=1) - timedelta(seconds=1)

# 3. meeting object: link from the Join action, title, stable key, seconds dropped
m = ns.to_meeting(ns.parse_toast(toast("Sprint planning", "in 10 minutes")), NOW + timedelta(seconds=17))
assert m.title == "Sprint planning" and m.link == "https://meet.google.com/abc-defg-hij"
assert m.start == (NOW + timedelta(minutes=10)).replace(second=0, microsecond=0) or m.start.second == 0

# 4. database path (stand-in schema): only Chrome/Edge + calendar rows survive; others are never returned
def ft(d): return int((d - ns.FILETIME_EPOCH).total_seconds() * 10_000_000)
db = Path(tempfile.mkdtemp()) / "wpndatabase.db"
con = sqlite3.connect(db)
con.execute("CREATE TABLE NotificationHandler (RecordId INTEGER PRIMARY KEY, PrimaryId TEXT)")
con.execute("CREATE TABLE Notification (Id INTEGER PRIMARY KEY, HandlerId INTEGER, Payload BLOB, ArrivalTime INTEGER)")
con.executemany("INSERT INTO NotificationHandler VALUES (?,?)", [(1, "Chrome"), (2, "Microsoft.Teams"), (3, "MSEdge")])
rows = [
    (1, toast("Standup", "in 10 minutes"), NOW - timedelta(minutes=9)),
    (1, toast("Standup", "in 1 minute"), NOW),                          # second pop-up, same meeting
    (1, toast("Secret HR thread", "private", site="mail.google.com", launch="https://mail.google.com/x"), NOW),
    (2, toast("Teams ping", "calendar.google.com mentioned here", site="teams"), NOW),   # other app: ignored
    (1, toast("Old one", "in 10 minutes"), NOW - timedelta(hours=5)),   # too old
    (3, toast("Edge meeting", "in 5 minutes"), NOW - timedelta(minutes=2)),
    (1, b"not xml at all", NOW),
]
con.executemany("INSERT INTO Notification (HandlerId, Payload, ArrivalTime) VALUES (?,?,?)",
                [(h, b, ft(t)) for h, b, t in rows])
con.commit(); con.close()
got = ns.NotificationSource(db_path=db).poll(now=NOW)
assert [x.title for x in got] == ["Standup", "Edge meeting"], [x.title for x in got]
assert not any("HR" in x.title or "Teams" in x.title for x in got)
# dismissing the pop-up (row removed from the DB) must not forget the meeting
c3 = sqlite3.connect(db); c3.execute("DELETE FROM Notification"); c3.commit(); c3.close()
src = ns.NotificationSource(db_path=db)
src._known = list(got)
assert [x.title for x in src.poll(now=NOW)] == ["Standup", "Edge meeting"]
assert src.poll(now=NOW + timedelta(minutes=30)) == []                       # long over -> forgotten

# 5. unexpected schema -> clear error, no guessing; missing DB -> FileNotFoundError
bad = Path(tempfile.mkdtemp()) / "x.db"
c2 = sqlite3.connect(bad); c2.execute("CREATE TABLE Other (a)"); c2.commit(); c2.close()
try: ns.calendar_notifications(bad, NOW); raise SystemExit("expected RuntimeError")
except RuntimeError as e: assert "unexpected" in str(e)
try: ns.calendar_notifications(bad.with_name("nope.db"), NOW); raise SystemExit("expected FileNotFoundError")
except FileNotFoundError: pass
print("notif_source tests passed")
