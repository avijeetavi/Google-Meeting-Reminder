import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # project root
from datetime import datetime, timedelta, timezone
from meetreminder.scheduler import Scheduler, Meeting

T0 = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
m = Meeting("a", "Standup", T0 + timedelta(minutes=30), T0 + timedelta(minutes=60))

def run(sched, start, end, step=10):
    shown, t = [], start
    while t <= end:
        for _, mins in sched.due([m], t):
            shown.append((int((t - T0).total_seconds()), mins))
        t += timedelta(seconds=step)
    return shown

# 1. 10..1 before start, 0 at start, then -1..-4 and NOTHING after 5 min past start
got = run(Scheduler(), T0, T0 + timedelta(minutes=45))
assert [x[1] for x in got] == [10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, -1, -2, -3, -4], got
assert got[0][0] == 20 * 60                    # exactly 10 min before
assert got[-1][0] < (30 + 5) * 60              # last reminder before start+5min
assert Scheduler().due([m], T0 + timedelta(minutes=35)) == []
assert Scheduler().expired([m], T0 + timedelta(minutes=35)) == ["a"]

# 2. Cancel stops everything
s = Scheduler(); t = T0 + timedelta(minutes=20)
first = [k for _, k in s.due([m], t)]; s.cancel("a")
rest = [k for i in range(1, 1500) for _, k in s.due([m], t + timedelta(seconds=i))]
assert first == [10] and rest == [], (first, rest)

# 3. Snooze 5 min then every minute again
s = Scheduler(); t = T0 + timedelta(minutes=20)
assert [k for _, k in s.due([m], t)] == [10]
t2 = t + timedelta(minutes=1)
assert [k for _, k in s.due([m], t2)] == [9]
s.snooze("a", t2)
assert s.due([m], t2 + timedelta(minutes=4, seconds=59)) == []
assert [k for _, k in s.due([m], t2 + timedelta(minutes=5))] == [4]
assert [k for _, k in s.due([m], t2 + timedelta(minutes=6))] == [3]

# 4. Snooze that ends after start+5min -> never shown again
s = Scheduler(); t = T0 + timedelta(minutes=34)
s.due([m], t); s.snooze("a", t)
assert s.due([m], t + timedelta(minutes=5)) == []

# 5. App started after the meeting began: reminds until start+5 min, then stops
s = Scheduler(); got = run(s, T0 + timedelta(minutes=32), T0 + timedelta(minutes=40))
assert [x[1] for x in got] == [-2, -3, -4], got

# 6. Snooze that runs past the start: 'started' is shown AT the start, snooze ignored
s = Scheduler(); t = T0 + timedelta(minutes=28)                     # meeting at +30
assert [k for _, k in s.due([m], t)] == [2]
s.snooze("a", t)                                                    # snooze would last until +33
assert s.due([m], T0 + timedelta(minutes=29, seconds=59)) == []     # still silent before the start
assert [k for _, k in s.due([m], T0 + timedelta(minutes=30))] == [0]          # started -> shown at once
assert "a" not in s.snoozed
assert [k for _, k in s.due([m], T0 + timedelta(minutes=31))] == [-1]         # then every minute
# 6b. Snooze pressed at 29:59 (1 s before start): shown at 30:00 right away
s = Scheduler(); t = T0 + timedelta(minutes=29, seconds=59)
s.due([m], t); s.snooze("a", t)
assert [k for _, k in s.due([m], T0 + timedelta(minutes=30))] == [0]
# 6c. A snooze that ends BEFORE the start still behaves as before
s = Scheduler(); t = T0 + timedelta(minutes=20); s.due([m], t); s.snooze("a", t)
assert s.due([m], t + timedelta(minutes=4, seconds=59)) == []
assert [k for _, k in s.due([m], t + timedelta(minutes=5))] == [5]
print("all scheduler tests passed")
