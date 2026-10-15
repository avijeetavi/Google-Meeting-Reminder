"""Drawing + route code for the flying plane and towed banner. No tkinter import,
so it can be tested headlessly with a fake canvas.

The whole assembly (plane, ropes, banner) is built ONCE per flight and then moved
by whole pixels -> text is never re-rendered while moving, so it stays crisp."""
import math
import random

VIOLET, CORAL, GOLD = "#6a3de8", "#ff5a3c", "#ffc83d"   # card: normal / last 2 minutes
MAX_TILT_DEG = 14


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rrect(c, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, tags="fx", **kw)


def pick_route(sw, sh, card_h, prev=None, rnd=random):
    """Random straight line across the screen: heights (yL, yR) at the left and
    right edges. Keeps the banner on-screen and differs clearly from `prev`."""
    lo, hi = card_h / 2 + 30, sh - card_h / 2 - 30
    if hi <= lo:
        return (sh / 2, sh / 2)
    max_dy = sw * math.tan(math.radians(MAX_TILT_DEG))
    route = None
    for _ in range(80):
        yl = rnd.uniform(lo, hi)
        yr = rnd.uniform(max(lo, yl - max_dy), min(hi, yl + max_dy))
        route = (yl, yr)
        if prev is None or abs(yl - prev[0]) + abs(yr - prev[1]) > 0.4 * (hi - lo):
            break
    return route


class Scene:
    S = 1.7          # plane scale
    CARD_W = 450
    CARD_H = 132
    ROPE = 46

    def __init__(self, fonts):
        self.f = fonts

    @property
    def left_extent(self):
        """Distance from the plane's centre x to the banner's far-left edge."""
        return 36 * self.S + self.ROPE + self.CARD_W + 8

    BTN_W, BTN_H, BTN_GAP = 130, 28, 16

    def _buttons(self, left, right, bot, minutes):
        """Hit rectangles for the buttons, centred in the card: Snooze + Cancel before the
        start (equal width, evenly spaced), Cancel alone once the meeting has started."""
        names = ["snooze", "cancel"] if minutes > 0 else ["cancel"]
        total = len(names) * self.BTN_W + (len(names) - 1) * self.BTN_GAP
        x = (left + right) / 2 - total / 2
        y1 = bot - 12
        out = {}
        for n in names:
            out[n] = (x, y1 - self.BTN_H, x + self.BTN_W, y1)
            x += self.BTN_W + self.BTN_GAP
        return out

    def _fit(self, font, text, width):
        while len(text) > 1 and font.measure(text) > width:
            text = text[:-2].rstrip() + "…"
        return text

    def build(self, c, px, py, theta, minutes, title, sub):
        """Create all canvas items (tag 'fx') with the plane centred at (px, py)
        flying along direction `theta` (radians, +ve = descending to the right).
        Returns {name: (x0, y0, x1, y1)} hit rectangles in canvas coordinates."""
        c.delete("fx")
        s, f = self.S, self.f
        ct, st = math.cos(theta), math.sin(theta)

        def P(dx, dy):
            x, y = dx * s, dy * s
            return (px + x * ct - y * st, py + x * st + y * ct)

        def poly(pts, **kw):
            c.create_polygon(*[v for p in pts for v in P(*p)], tags="fx", **kw)

        def ell(cx, cy, rx, ry, n=22, **kw):
            poly([(cx + rx * math.cos(2 * math.pi * i / n),
                   cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)], **kw)

        hot = minutes <= 2
        base = CORAL if hot else VIOLET
        light = mix(base, "#ffffff", 0.16)
        soft = mix(base, "#ffffff", 0.78)

        # banner sits on the flight line, trailing behind the plane (kept upright)
        D = 36 * s + self.ROPE
        right = px - D
        left = right - self.CARD_W
        cy = py - (D + self.CARD_W / 2) * math.tan(theta)
        top = cy - self.CARD_H / 2
        bot = top + self.CARD_H
        tail = P(-30, 0)

        c.create_line(*tail, right, top + 16, fill="#e9efff", width=2, tags="fx")
        c.create_line(*tail, right, bot - 16, fill="#e9efff", width=2, tags="fx")

        rrect(c, left, top, right, bot, 16, fill=base, outline=mix(base, "#ffffff", 0.55), width=2)
        rrect(c, left + 3, top + 3, right - 3, top + 46, 13, fill=light, outline="")
        head = "Meeting started" if minutes <= 0 else \
            ("Meeting in 1 min" if minutes == 1 else f"Meeting in {minutes} min")
        pad = 18
        c.create_text(left + pad, top + 25, text=head, anchor="w", font=f.big,
                      fill="#ffffff", tags="fx")
        c.create_text(left + pad, top + 60,
                      text=self._fit(f.med, title, self.CARD_W - 2 * pad), anchor="w",
                      font=f.med, fill="#ffffff", tags="fx")
        c.create_text(left + pad, top + 79, text=sub, anchor="w", font=f.small,
                      fill=soft, tags="fx")

        rects = {"card": (left, top, right, bot)}
        for name, r in self._buttons(left, right, bot, minutes).items():
            color, label, fg = (GOLD, "Snooze 5 min", "#3a2600") if name == "snooze" else \
                (mix(base, "#000000", 0.35), "Cancel", "#ffffff")
            rrect(c, *r, 8, fill=color, outline="")
            c.create_text((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, text=label, font=f.btn,
                          fill=fg, tags="fx")
            rects[name] = r

        # the plane (nose points along the flight direction)
        poly([(-26, -4), (-36, -22), (-24, -22), (-12, -4)], fill="#c9d6f5", outline="")
        poly([(-4, -3), (-14, -14), (-5, -14), (8, -3)], fill="#aebde6", outline="")
        ell(0, 0, 30, 8, fill="#ffffff", outline="")
        ell(19, -2, 5, 3.5, fill="#5aa9ff", outline="")
        for wx in range(-16, 10, 8):
            ell(wx + 2, -2, 2, 2, n=10, fill="#8ea6d9", outline="")
        poly([(-6, 3), (-20, 24), (-7, 24), (12, 3)], fill="#dfe8ff", outline="#aebde6")
        ell(4, 15.5, 6, 3.5, n=14, fill="#7d8db8", outline="")
        return rects

    def build_alert(self, c, cx, cy, title, sub, lit):
        """'Meeting started' card fixed at the centre (cx, cy) with a glowing on/off lamp effect.
        lit=True: bright card with a glow; lit=False: the same card dimmed. Returns hit rects."""
        c.delete("fx")
        f, W, H = self.f, self.CARD_W, self.CARD_H
        left, right, top, bot = cx - W / 2, cx + W / 2, cy - H / 2, cy + H / 2
        off = mix(CORAL, "#14081f", 0.80)
        base = CORAL if lit else off
        txt = "#ffffff" if lit else mix("#ffffff", off, 0.62)
        soft = mix(base, "#ffffff", 0.78) if lit else mix("#ffffff", off, 0.72)
        if lit:                                           # glow rings around the card
            for pad, wd, t in ((22, 3, 0.80), (14, 3, 0.62), (7, 3, 0.35)):
                rrect(c, left - pad, top - pad, right + pad, bot + pad, 16 + pad, fill="",
                      outline=mix(CORAL, "#ffffff", t), width=wd)
        rrect(c, left, top, right, bot, 16, fill=base,
              outline=mix(base, "#ffffff", 0.55 if lit else 0.15), width=2)
        rrect(c, left + 3, top + 3, right - 3, top + 46, 13,
              fill=mix(base, "#ffffff", 0.16 if lit else 0.06), outline="")
        pad = 18
        c.create_text(left + pad, top + 25, text="Meeting started", anchor="w", font=f.big,
                      fill=txt, tags="fx")
        c.create_text(left + pad, top + 60, text=self._fit(f.med, title, W - 2 * pad), anchor="w",
                      font=f.med, fill=txt, tags="fx")
        c.create_text(left + pad, top + 79, text=sub, anchor="w", font=f.small, fill=soft, tags="fx")
        rects = {"card": (left - 22, top - 22, right + 22, bot + 22)}
        for name, r in self._buttons(left, right, bot, 0).items():
            color = mix(base, "#000000", 0.35) if lit else mix(mix(CORAL, "#000000", 0.35), off, 0.6)
            rrect(c, *r, 8, fill=color, outline="")
            c.create_text((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, text="Cancel", font=f.btn,
                          fill="#ffffff" if lit else mix("#ffffff", off, 0.5), tags="fx")
            rects[name] = r
        return rects
