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
            r = sc.build(c, 900.0, 500.0, math.radians(deg), minutes, title, "Starts 7:14 PM")
            card = r["card"]
            assert "join" not in r                                # no Join button any more
            names = ("cancel",) if minutes <= 0 else ("snooze", "cancel")
            assert ("snooze" in r) == (minutes > 0), minutes     # no Snooze once started
            for n in names:
                b = r[n]
                assert card[0] < b[0] < b[2] < card[2] and card[1] < b[1] < b[3] < card[3]
            ca = r["cancel"]
            assert abs((card[2] - ca[2]) - 18) < 1e-6                    # Cancel: bottom-RIGHT corner
            assert abs((card[3] - ca[3]) - 12) < 1e-6
            if "snooze" in r:                                            # Snooze: bottom-LEFT corner
                sn = r["snooze"]
                assert abs((sn[0] - card[0]) - 18) < 1e-6 and abs(sn[3] - ca[3]) < 1e-6
                assert sn[2] < ca[0] and abs((sn[2] - sn[0]) - (ca[2] - ca[0])) < 1e-6
            assert card[2] < 900 - 36 * sc.S           # banner trails behind the plane
r = sc.build(c, 900.0, 500.0, 0.0, 0, "x", "s")
assert "Meeting started" in [i[2]["text"] for i in c.items if i[0] == "text"]
r = sc.build(c, 900.0, 500.0, 0.0, -3, "x", "s")
assert "Meeting started" in [i[2]["text"] for i in c.items if i[0] == "text"]
r = sc.build(c, 900.0, 500.0, 0.0, 7, "x", "s")
assert "Meeting in 7 min" in [i[2]["text"] for i in c.items if i[0] == "text"]

# 1b. 'meeting started' lamp card: centred, only Cancel, lit and dim differ but share geometry
cx, cy = 960.0, 516.0
rl = sc.build_alert(c, cx, cy, "Standup", "Started at 7:14 PM", True); lit_items = list(c.items)
rd = sc.build_alert(c, cx, cy, "Standup", "Started at 7:14 PM", False); dim_items = list(c.items)
assert rl == rd and set(rl) == {"card", "cancel"}, rl
x0, y0, x1, y1 = rl["card"]
assert abs((x0 + x1) / 2 - cx) < 1e-6 and abs((y0 + y1) / 2 - cy) < 1e-6   # fixed in the centre
cb = rl["cancel"]
assert x0 < cb[0] < cb[2] < x1 and cb[2] > cx                           # Cancel sits bottom-right
colours = lambda items: [i[2].get("fill") for i in items if i[0] == "text"]
assert colours(lit_items) != colours(dim_items)                            # the lamp really changes
assert len(lit_items) > len(dim_items)                                     # glow rings only when lit
assert "Meeting started" in [i[2]["text"] for i in lit_items if i[0] == "text"]

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
