import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # project root
"""Headless test of Calendar API event parsing (no Google libraries or network needed)."""
from meetreminder.gcal_api import parse_events

def ev(id, title, start, end="2026-10-13T15:00:00+05:30", **kw):
    d = {"id": id, "summary": title, "start": {"dateTime": start}, "end": {"dateTime": end}}
    d.update(kw); return d

items = [
    ev("a", "Standup", "2026-10-13T10:00:00+05:30", hangoutLink="https://meet.google.com/abc-defg-hij"),
    ev("b", "Via conferenceData", "2026-10-13T11:00:00Z",
       conferenceData={"entryPoints": [{"entryPointType": "video", "uri": "https://meet.google.com/xyz-abcd-efg"}]}),
    ev("c", "Link in description", "2026-10-13T12:00:00Z",
       description="Join: https://meet.google.com/qqq-wwww-eee now"),
    ev("d", "Zoom only", "2026-10-13T13:00:00Z", location="https://zoom.us/j/123"),
    {"id": "e", "summary": "All day", "start": {"date": "2026-10-13"}, "end": {"date": "2026-10-14"},
     "hangoutLink": "https://meet.google.com/aaa-bbbb-ccc"},
    ev("f", "Cancelled", "2026-10-13T14:00:00Z", status="cancelled", hangoutLink="https://meet.google.com/aaa-bbbb-ccc"),
    ev("g", "Declined by me", "2026-10-13T14:30:00Z", hangoutLink="https://meet.google.com/aaa-bbbb-ccc",
       attendees=[{"email": "x@y.com", "responseStatus": "accepted"},
                  {"email": "me@y.com", "self": True, "responseStatus": "declined"}]),
    ev("h", "Accepted by me", "2026-10-13T16:00:00Z", hangoutLink="https://meet.google.com/aaa-bbbb-ccc",
       attendees=[{"email": "me@y.com", "self": True, "responseStatus": "accepted"}]),
    ev("rec_20261013", "Recurring (today)", "2026-10-13T09:00:00Z", hangoutLink="https://meet.google.com/rrr-rrrr-rrr"),
    ev("rec_20261014", "Recurring (tomorrow)", "2026-10-14T09:00:00Z", hangoutLink="https://meet.google.com/rrr-rrrr-rrr"),
    {"id": "i", "summary": "Home", "eventType": "workingLocation", "start": {"dateTime": "2026-10-13T08:00:00Z"},
     "end": {"dateTime": "2026-10-13T09:00:00Z"}, "hangoutLink": "https://meet.google.com/aaa-bbbb-ccc"},
    ev("j", None, "2026-10-13T17:00:00Z", hangoutLink="https://meet.google.com/aaa-bbbb-ccc"),
]
got = parse_events(items)
titles = [m.title for m in got]
assert titles == ["Standup", "Recurring (today)", "Via conferenceData", "Link in description",
                  "Accepted by me", "(No title)", "Recurring (tomorrow)"], titles
assert len({m.key for m in got}) == len(got)                      # recurring instances have distinct keys
standup = next(m for m in got if m.title == "Standup")
assert standup.start.isoformat() == "2026-10-13T04:30:00+00:00"   # +05:30 converted to UTC
assert standup.link == "https://meet.google.com/abc-defg-hij"
assert all(m.start.tzinfo is not None for m in got)
assert "Zoom only" in [m.title for m in parse_events(items, only_meet=False)]
assert "All day" not in [m.title for m in parse_events(items, only_meet=False)]
print("gcal_api parse tests passed")

# ---- network path with stubbed Google libraries (pagination + error mapping) --------------
import sys, types, tempfile
from pathlib import Path
from meetreminder import gcal_api

class RefreshError(Exception): pass
calls = []
class Resp:
    def __init__(s, code, data): s.status_code, s._d, s.text = code, data, str(data)
    def json(s): return s._d
class Session:
    mode = "ok"
    def __init__(s, creds): pass
    def get(s, url, params=None, timeout=None):
        calls.append(dict(params))
        if Session.mode == "refresh": raise RefreshError("invalid_grant")
        if Session.mode == "http": return Resp(403, {"error": "API not enabled"})
        if "pageToken" not in params:
            return Resp(200, {"items": [ev("p1", "Page one", "2026-10-13T10:00:00Z",
                                           hangoutLink="https://meet.google.com/aaa-bbbb-ccc")],
                              "nextPageToken": "T2"})
        return Resp(200, {"items": [ev("p2", "Page two", "2026-10-13T11:00:00Z",
                                       hangoutLink="https://meet.google.com/aaa-bbbb-ccc")]})
class Creds:
    @staticmethod
    def from_authorized_user_file(path, scopes): return Creds()
    def to_json(self): return "{}"
def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
mod("google"); mod("google.auth"); mod("google.auth.exceptions", RefreshError=RefreshError)
mod("google.auth.transport"); mod("google.auth.transport.requests", AuthorizedSession=Session)
mod("google.oauth2"); mod("google.oauth2.credentials", Credentials=Creds)

base = Path(tempfile.mkdtemp())
try:
    gcal_api.fetch_meetings(base); raise SystemExit("expected AuthRequired when not signed in")
except gcal_api.AuthRequired:
    pass
(base / "token.json").write_text("{}")
got = gcal_api.fetch_meetings(base)
assert [m.title for m in got] == ["Page one", "Page two"], got
assert len(calls) == 2 and calls[1]["pageToken"] == "T2" and calls[0]["singleEvents"] == "true"
assert calls[0]["orderBy"] == "startTime" and calls[0]["timeMin"].endswith("Z")
Session.mode = "refresh"
try:
    gcal_api.fetch_meetings(base); raise SystemExit("expected AuthRequired on RefreshError")
except gcal_api.AuthRequired:
    pass
Session.mode = "http"
try:
    gcal_api.fetch_meetings(base); raise SystemExit("expected RuntimeError on HTTP 403")
except RuntimeError as e:
    assert "403" in str(e)
assert gcal_api.sign_out(base) and not gcal_api.sign_out(base)
print("gcal_api network-path tests passed")
