"""Full-screen popup on a transparent, click-through overlay.

Before the meeting starts: a plane flies left -> right along a straight line (a different random
line every time), towing a banner with the countdown, title, start time and Snooze / Cancel buttons.
Hover the banner to freeze the flight so the buttons are easy to click.

Once the meeting has started: no flight. A "Meeting started" card is fixed in the centre of the
screen and blinks like a lamp (bright / dim) with a Cancel button, until Cancelled or 5 min after
the start. Hovering the card keeps it lit so it is easy to read and click."""
import logging
import math
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from types import SimpleNamespace

from .scene import Scene, pick_route

KEY = "#010101"        # colour made transparent on Windows (and click-through)
FRAME_S = 1 / 60       # fixed 60 fps cadence
CRUISE_STEP = 2        # px per frame while the whole banner is on screen (120 px/s: readable)
FAST_STEP = 6          # px per frame while entering / leaving (360 px/s)
BLINK_ON, BLINK_OFF = 0.7, 0.5   # seconds lit / dim for the "meeting started" lamp


def work_area(root):
    """(x0, y0, x1, y1) of the usable screen, i.e. excluding the taskbar."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
            return r.left, r.top, r.right, r.bottom
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 48


_timer_set = False


def high_res_timer():
    """Windows rounds Tk's timers to ~15.6 ms, which makes motion uneven (text looks
    smeared). Ask for 1 ms resolution so frames really arrive every ~16 ms."""
    global _timer_set
    if sys.platform == "win32" and not _timer_set:
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
            _timer_set = True
        except Exception:
            pass


class Popup(tk.Toplevel):
    _last_route = None          # remembered so the next flight takes a different line

    def __init__(self, root, meeting, minutes, on_snooze, on_cancel):
        super().__init__(root)
        high_res_timer()
        self.m = meeting
        self.cb_snooze, self.cb_cancel = on_snooze, on_cancel
        self.alive, self.done = True, True
        self.static, self.lit, self.t_blink = False, True, 0.0   # static = 'meeting started' lamp mode
        self.rects, self.minutes = {}, minutes
        self.x, self.next_t, self.ipos = 0, time.perf_counter(), (0, 0)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        x0, y0, x1, y1 = work_area(root)
        self.sw, self.sh = x1 - x0, y1 - y0
        self.canvas = tk.Canvas(self, width=self.sw, height=self.sh, bg=KEY,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        try:
            self.attributes("-transparentcolor", KEY)
        except tk.TclError:                        # non-Windows fallback: opaque sky
            self.canvas.configure(bg="#0b1030")
        self.geometry(f"{self.sw}x{self.sh}+{x0}+{y0}")

        fonts = SimpleNamespace(
            big=tkfont.Font(root=self, family="Segoe UI", size=17, weight="bold"),
            med=tkfont.Font(root=self, family="Segoe UI", size=12, weight="bold"),
            small=tkfont.Font(root=self, family="Segoe UI", size=9),
            btn=tkfont.Font(root=self, family="Segoe UI", size=10, weight="bold"))
        self.scene = Scene(fonts)
        self.start_x = -self.scene.left_extent - 20
        self.end_x = self.sw + self.scene.left_extent + 20
        self.canvas.bind("<Button-1>", self._click)

        self.update_minutes(minutes)
        self._animate()

    # ---- called by the app every minute ----------------------------
    def update_minutes(self, minutes):
        self.minutes = minutes
        local = self.m.start.astimezone().strftime("%I:%M %p").lstrip("0")
        self.title_text = self.m.title
        verb = "Started at" if minutes <= 0 else "Starts at"
        self.sub_text = f"{verb} {local}" + ("  ·  Google Meet" if self.m.link else "")
        if minutes <= 0:                           # started: fixed, blinking card in the centre
            if not self.static:
                self._enter_static()
        elif self.done:                            # previous pass finished: new flight
            self._start_flight()
        else:                                      # still flying/frozen: just refresh text
            self._rebuild()

    def _enter_static(self):
        """Stop any flight and show the centred blinking 'Meeting started' card."""
        self.static, self.done = True, True        # done=True also idles the flight code
        self.lit, self.t_blink = True, time.perf_counter()
        logging.info("started-card: %s", self.m.title)
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        self._draw_static()

    def _draw_static(self):
        self.rects = self.scene.build_alert(self.canvas, self.sw / 2, self.sh / 2,
                                            self.title_text, self.sub_text, self.lit)

    def _start_flight(self):
        yl, yr = pick_route(self.sw, self.sh, Scene.CARD_H, Popup._last_route)
        Popup._last_route = (yl, yr)
        self.slope = (yr - yl) / self.sw           # straight line: y = yl + slope * x
        self.theta = math.atan(self.slope)
        logging.info("flight: screen %dx%d, route y %.0f -> %.0f", self.sw, self.sh, yl, yr)
        self.y_left = yl
        self.x, self.next_t, self.done = self.start_x, time.perf_counter(), False
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        self._rebuild()

    def _line(self):
        return self.x, self.y_left + self.slope * self.x

    def _rebuild(self):
        x, y = self._line()
        self.ipos = (round(x), round(y))
        self.rects = self.scene.build(self.canvas, self.ipos[0], self.ipos[1], self.theta,
                                      self.minutes, self.title_text, self.sub_text)

    # ---- animation --------------------------------------------------
    def _hovering(self):
        card = self.rects.get("card")
        if not card:
            return False
        mx = self.winfo_pointerx() - self.winfo_rootx()
        my = self.winfo_pointery() - self.winfo_rooty()
        return card[0] - 8 <= mx <= card[2] + 8 and card[1] - 8 <= my <= card[3] + 8

    def _step(self):
        """Pixels to advance this frame: fast while entering/leaving, slow while the
        banner is fully on screen (so the text is readable), smooth ramps between."""
        x, ramp = self.x, 220.0
        full_in = self.scene.left_extent                 # banner fully visible from here...
        full_out = self.sw + 36 * Scene.S + Scene.ROPE   # ...until its right edge leaves
        if x < full_in - ramp or x > full_out + ramp:
            t = 1.0
        elif x < full_in:
            t = (full_in - x) / ramp
        elif x <= full_out:
            t = 0.0
        else:
            t = (x - full_out) / ramp
        t = t * t * (3 - 2 * t)
        return max(CRUISE_STEP, round(CRUISE_STEP + (FAST_STEP - CRUISE_STEP) * t))

    def _animate(self):
        if not self.alive:
            return
        if self.static:                            # lamp: lit BLINK_ON s, dim BLINK_OFF s, repeat
            phase = (time.perf_counter() - self.t_blink) % (BLINK_ON + BLINK_OFF)
            lit = phase < BLINK_ON or self._hovering()
            if lit != self.lit:
                self.lit = lit
                self._draw_static()
            self.after(40, self._animate)
            return
        if self.done:
            self.after(250, self._animate)
            return
        now = time.perf_counter()
        if not self._hovering():                   # hover = freeze so buttons are clickable
            if self.x > self.end_x:                # flew off the right edge
                self.done, self.rects = True, {}
                self.canvas.delete("fx")
                self.withdraw()
                self.after(250, self._animate)
                return
            self.x += self._step()                 # whole pixels, same step every frame
            x, y = self._line()
            ix, iy = round(x), round(y)
            dx, dy = ix - self.ipos[0], iy - self.ipos[1]
            if dx or dy:                           # whole-pixel move: text stays crisp
                self.canvas.move("fx", dx, dy)
                self.rects = {k: (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)
                              for k, r in self.rects.items()}
                self.ipos = (ix, iy)
        self.next_t += FRAME_S                     # fixed cadence, no drift
        if self.next_t < now - 3 * FRAME_S:
            self.next_t = now
        self.after(max(1, int((self.next_t - time.perf_counter()) * 1000)), self._animate)

    # ---- actions ----------------------------------------------------
    def _click(self, e):
        for name in ("snooze", "cancel"):
            r = self.rects.get(name)
            if r and r[0] <= e.x <= r[2] and r[1] <= e.y <= r[3]:
                self.close()
                (self.cb_snooze if name == "snooze" else self.cb_cancel)(self.m)
                return

    def close(self):
        self.alive = False
        self.destroy()
