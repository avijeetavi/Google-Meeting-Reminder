"""Pure scheduling logic (no GUI) so it can be unit-tested."""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

LEAD_MINUTES = 10
SNOOZE_SECONDS = 5 * 60
GRACE_SECONDS = 5 * 60  # keep reminding every minute until 5 min AFTER the start, then stop


@dataclass
class Meeting:
    key: str
    title: str
    start: datetime          # tz-aware UTC
    end: datetime
    link: str = ""


@dataclass
class Scheduler:
    cancelled: set = field(default_factory=set)
    snoozed: dict = field(default_factory=dict)      # key -> datetime until
    last_bucket: dict = field(default_factory=dict)  # key -> last minutes shown

    def cancel(self, key):
        self.cancelled.add(key)
        self.snoozed.pop(key, None)

    def snooze(self, key, now):
        self.snoozed[key] = now + timedelta(seconds=SNOOZE_SECONDS)
        self.last_bucket.pop(key, None)  # fire again right after snooze ends

    def due(self, meetings, now):
        """Return [(meeting, minutes_left)] that should be (re)shown now.
        minutes_left <= 0 means the meeting has already started. A snooze never delays the
        "started" reminder: at the start time it is shown at once, whatever the snooze says."""
        out = []
        for m in meetings:
            if m.key in self.cancelled:
                continue
            secs = (m.start - now).total_seconds()
            if secs > LEAD_MINUTES * 60 or secs <= -GRACE_SECONDS:
                continue
            until = self.snoozed.get(m.key)
            if until is not None:
                if secs > 0 and now < until:
                    continue                     # still snoozed and the meeting has not started yet
                self.snoozed.pop(m.key, None)   # snooze over, or the meeting STARTED: ignore snooze
            mins = math.ceil(secs / 60)        # 10..1 before start, 0 and negative once started
            if self.last_bucket.get(m.key) != mins:
                self.last_bucket[m.key] = mins
                out.append((m, mins))
        return out

    def expired(self, meetings, now):
        """Keys whose popup should be closed because the meeting is over its grace window."""
        return [m.key for m in meetings
                if (m.start - now).total_seconds() <= -GRACE_SECONDS]
