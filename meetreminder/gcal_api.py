"""Official Google Calendar API source (read-only). Replaces the secret iCal URL.

* Scope: calendar.events.readonly (can read events, cannot change or delete anything).
* Sign-in: standard OAuth "installed app" flow. Your browser opens, you sign in with your
  Google account and approve; Google sends the result to http://localhost on a random port.
* Files (in %APPDATA%\\MeetReminder, never in the code folder):
    client_secret.json - the OAuth client you download from Google Cloud (see GOOGLE_API_SETUP.md)
    token.json         - created after you sign in; holds a refresh token (delete = sign out)
* Google libraries are imported lazily, so parsing/tests run without them.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .scheduler import Meeting

SCOPES = ["https://www.googleapis.com/auth/calendar.events.readonly"]
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MEET_RE = re.compile(r"https://meet\.google\.com/[a-z0-9\-]+(?:\?[^\s\"<>]*)?", re.I)


class AuthRequired(Exception):
    """No valid Google sign-in (never signed in, token revoked, or expired for good)."""


def client_secret_path(base: Path, project_dir: Path):
    for p in (base / "client_secret.json", project_dir / "client_secret.json"):
        if p.exists():
            return p
    return None


def _save_token(base: Path, creds):
    base.mkdir(parents=True, exist_ok=True)
    p = base / "token.json"
    p.write_text(creds.to_json(), "utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def load_credentials(base: Path):
    p = base / "token.json"
    if not p.exists():
        return None
    from google.oauth2.credentials import Credentials
    return Credentials.from_authorized_user_file(str(p), SCOPES)


def authorize(base: Path, project_dir: Path):
    """Interactive sign-in (opens the browser). Saves token.json. Returns credentials."""
    secret = client_secret_path(base, project_dir)
    if secret is None:
        raise FileNotFoundError(
            "client_secret.json not found.\n\nFollow GOOGLE_API_SETUP.md, then save the downloaded "
            f"file as:\n{base / 'client_secret.json'}")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(
        port=0, prompt="consent",
        authorization_prompt_message="Opening your browser to sign in to Google ...",
        success_message="Meet Reminder is connected. You can close this tab.")
    _save_token(base, creds)
    return creds


def sign_out(base: Path) -> bool:
    try:
        (base / "token.json").unlink()
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------- parsing (pure)
def _dt(obj):
    """{'dateTime': ...} -> aware UTC datetime; all-day ({'date': ...}) -> None."""
    s = (obj or {}).get("dateTime")
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _meet_link(ev) -> str:
    if ev.get("hangoutLink"):
        return ev["hangoutLink"]
    for ep in (ev.get("conferenceData") or {}).get("entryPoints", []) or []:
        if ep.get("entryPointType") == "video" and "meet.google.com" in (ep.get("uri") or ""):
            return ep["uri"]
    m = MEET_RE.search(" ".join(str(ev.get(k) or "") for k in ("location", "description")))
    return m.group(0) if m else ""


def parse_events(items, only_meet=True):
    """Convert Calendar API event dicts into Meeting objects (sorted by start)."""
    out = []
    for ev in items:
        if ev.get("status") == "cancelled" or ev.get("eventType") == "workingLocation":
            continue
        if any(a.get("self") and a.get("responseStatus") == "declined"
               for a in ev.get("attendees") or []):
            continue
        start = _dt(ev.get("start"))
        if start is None:                                   # all-day event
            continue
        link = _meet_link(ev)
        if only_meet and not link:
            continue
        end = _dt(ev.get("end")) or start + timedelta(hours=1)
        out.append(Meeting(key=f"{ev.get('id', '')}|{start.isoformat()}",
                           title=ev.get("summary") or "(No title)",
                           start=start, end=end, link=link))
    return sorted(out, key=lambda m: m.start)


# ---------------------------------------------------------------- network
def fetch_meetings(base: Path, only_meet=True, hours=24, now=None):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import AuthorizedSession
    creds = load_credentials(base)
    if creds is None:
        raise AuthRequired("not signed in - run: python meet_reminder.py --auth")
    now = now or datetime.now(timezone.utc)
    iso = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session, items, token = AuthorizedSession(creds), [], None
    try:
        while True:
            params = {"timeMin": iso(now - timedelta(hours=1)), "timeMax": iso(now + timedelta(hours=hours)),
                      "singleEvents": "true", "orderBy": "startTime", "maxResults": 250}
            if token:
                params["pageToken"] = token
            r = session.get(EVENTS_URL, params=params, timeout=25)
            if r.status_code != 200:
                raise RuntimeError(f"Google Calendar API HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            items += data.get("items", [])
            token = data.get("nextPageToken")
            if not token:
                break
    except RefreshError as e:
        raise AuthRequired(f"Google sign-in expired or was revoked ({e}) - run: python meet_reminder.py --auth")
    _save_token(base, creds)                                # keeps a refreshed access token
    return parse_events(items, only_meet)
