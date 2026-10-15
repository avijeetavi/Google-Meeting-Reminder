import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # project root
"""Headless tests: banner geometry for any flight angle + random route picking."""
import math, random
from meetreminder.scene import Scene, pick_route, MAX_TILT_DEG

class Font:
    def measure(self, s): return 8 * len(s)

class Fake:
    def __init__(self): self.items = []
    def delete(self, *_): self.items = []
    def create_polygon(self, *a, **k): self.items.append(("poly", a, k))
    def create_line(self, *a, **k): self.items.append(("line", a, k))
    def create_text(self, *a, **k): self.items.append(("text", a, k))

class F: big = med = small = btn = Font()
sc, c = Scene(F()), Fake()

# 1. geometry holds for every tilt, minute (incl. already-started) and title length
for deg in range(-MAX_TILT_DEG, MAX_TILT_DEG + 1, 2):
    for minutes in range(10, -5, -1):
        for title in ("Standup", "A very long meeting title " * 6):
            r = sc.build(c, 900.0, 500.0, math.radians(deg), minutes, title, "Starts 7:14 PM", True)
            card = r["card"]
            names = ("join", "cancel") if minutes <= 0 else ("join", "snooze", "cancel")
            assert ("snooze" in r) == (minutes > 0), minutes     # no Snooze once started
            for n in names:
                b = r[n]
                assert card[0] < b[0] < b[2] < card[2] and card[1] < b[1] < b[3] < card[3]
            assert r["join"][2] < r["cancel"][0]
            if "snooze" in r:
                assert r["join"][2] < r["snooze"][0] < r["snooze"][2] < r["cancel"][0]
            assert card[2] < 900 - 36 * sc.S           # banner trails behind the plane
    texts = [i[2]["text"] for i in c.items if i[0] == "text"]
r = sc.build(c, 900.0, 500.0, 0.0, 0, "x", "s", True)
assert "Meeting started" in [i[2]["text"] for i in c.items if i[0] == "text"]
r = sc.build(c, 900.0, 500.0, 0.0, -3, "x", "s", True)
assert "Meeting started" in [i[2]["text"] for i in c.items if i[0] == "text"]
r = sc.build(c, 900.0, 500.0, 0.0, 7, "x", "s", True)
assert "Meeting in 7 min" in [i[2]["text"] for i in c.items if i[0] == "text"]

# 2. routes: straight, bounded, gently tilted, and different every time
rnd = random.Random(1)
sw, sh = 1920, 1032
lo, hi = sc.CARD_H / 2 + 30, sh - sc.CARD_H / 2 - 30
prev, routes = None, []
for _ in range(500):
    r = pick_route(sw, sh, sc.CARD_H, prev, rnd)
    assert lo <= r[0] <= hi and lo <= r[1] <= hi, r
    assert abs(math.degrees(math.atan((r[1] - r[0]) / sw))) <= MAX_TILT_DEG + 1e-6
    if prev:
        assert abs(r[0] - prev[0]) + abs(r[1] - prev[1]) > 0.4 * (hi - lo), (prev, r)
    routes.append(r); prev = r
assert len({round(r[0] / 50) for r in routes}) > 8       # real variety
# small screen still works
assert pick_route(1366, 600, sc.CARD_H, None, rnd)
print("scene tests passed")
