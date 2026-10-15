"""Meet Reminder - background Google Meet notifier (Windows-first, pure Tkinter).

Daily use (PowerShell, in the project folder):
      python  meet_reminder.py --start    start in the background + auto-start at every sign-in
      python  meet_reminder.py --stop     stop the app AND remove auto-start
      python  meet_reminder.py --status   is it running? is auto-start set up?

Testing:
      python  meet_reminder.py --demo                fake meeting in 10 min, to preview the plane
      python  meet_reminder.py --demo-minutes=-1     fake meeting that started 1 min ago
      python  meet_reminder.py --probe-notifications show what the Chrome pop-up source can see

Google Calendar API source (once IT provides client_secret.json):
      python  meet_reminder.py --source=api|notif|ics   choose the calendar source (--start selects notif)
      python  meet_reminder.py --auth       sign in to Google Calendar, one time
      python  meet_reminder.py --signout    delete the saved Google sign-in
      python  meet_reminder.py --install    auto-start + run now, keeping the chosen source

Low level: `pythonw meet_reminder.py` runs in the background without a console window.
(--uninstall = --stop, --quickstart = --start: old names, still accepted.)
"""
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import simpledialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent))
from meetreminder.scheduler import Scheduler, Meeting

APP = "MeetReminder"
BASE = Path(os.environ.get("APPDATA", Path.home() / ".config")) / APP
CONFIG, STATE = BASE / "config.json", BASE / "state.json"
LOG = Path(__file__).resolve().parent / "meet_reminder.log"   # next to the code
REFRESH_SECONDS, TICK_MS, PORT = 300, 1000, 47653
DEFAULT_CFG = {"source": "api",      # "api" = official Google Calendar API (default), "ics" = secret iCal URL
               "ics_url": "", "my_email": "", "only_meet": True}


def load_json(p, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return dict(default) if isinstance(default, dict) else default


def save_json(p, data):
    BASE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), "utf-8")


def startup_vbs():
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/MeetReminder.vbs"


def install(start_now=True):
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    pyw = pyw if pyw.exists() else py
    script = Path(__file__).resolve()
    vbs = ('CreateObject("WScript.Shell").Run """%s"" ""%s""", 0, False\r\n' % (pyw, script))
    startup_vbs().write_text(vbs, "utf-8")
    print("Installed auto-start:", startup_vbs())
    print("It starts at every sign-in (after restart, shutdown or sign-out).\n"
          "Sleep/hibernate: the app keeps running and refreshes the calendar on wake.")
    if start_now:
        subprocess.Popen([str(pyw), str(script)], creationflags=0x08000000)


def quickstart():
    """One command: use Chrome Calendar pop-ups (temporary source), check Windows can be read, auto-start + run now."""
    cfg = {**DEFAULT_CFG, **load_json(CONFIG, {})}
    cfg["source"] = "notif"
    save_json(CONFIG, cfg)
    print("1/3 Calendar source set to 'notif' (Chrome Calendar pop-ups).")
    try:
        from meetreminder.notif_source import NotificationSource
        n = len(NotificationSource().poll())
        print(f"2/3 Windows notification database is readable ({n} Calendar pop-up(s) seen right now).")
    except Exception as e:                       # not fatal: the app retries every 15 s
        print(f"2/3 WARNING: could not read the notification database yet: {e}")
    print("3/3 Installing auto-start and starting in the background ...")
    install()
    print("\nDone. You can close this window. Check: python meet_reminder.py --status   Stop: python meet_reminder.py --stop")


def status():
    vbs = startup_vbs() if sys.platform == "win32" else None
    print("Auto-start entry :", ("present - " + str(vbs)) if vbs and vbs.exists() else "NOT installed (run --start)")
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=2).close()
        print("Running now      : yes (one instance)")
    except OSError:
        print("Running now      : no")
    cfg = {**DEFAULT_CFG, **load_json(CONFIG, DEFAULT_CFG)}
    if cfg["source"] == "notif":
        print("Calendar source  : Chrome Calendar pop-ups (temporary; Chrome must be running)")
        return
    if cfg["source"] == "ics":
        print("Calendar source  : secret iCal URL -", "set" if cfg["ics_url"] else "NOT set (the app asks for it when started with --install)")
    else:
        print("Calendar source  : Google Calendar API -",
              "signed in" if (BASE / "token.json").exists() else "NOT signed in (run --auth)")
        print("client_secret    :", "found" if ((BASE / "client_secret.json").exists() or
              (Path(__file__).resolve().parent / "client_secret.json").exists())
              else "missing (see GOOGLE_API_SETUP.md)")
    try:
        print("Last log lines   :")
        for line in LOG.read_text("utf-8").splitlines()[-6:]:
            print("   ", line)
    except OSError:
        pass


def cmd_auth():
    """Interactive Google sign-in (opens the browser) and a test read of the next 24 h."""
    try:
        from meetreminder import gcal_api
        gcal_api.authorize(BASE, Path(__file__).resolve().parent)
        meetings = gcal_api.fetch_meetings(BASE)
    except ImportError:
        print("Google libraries missing. Run: pip install -r requirements.txt")
        return 1
    except FileNotFoundError as e:
        print(e)
        return 1
    except Exception as e:
        logging.exception("auth failed")
        print("Sign-in failed:", e)
        return 1
    print(f"Connected. {len(meetings)} Google Meet meeting(s) in the next 24 hours:")
    for m in meetings[:8]:
        print("  ", m.start.astimezone().strftime("%a %d %b %I:%M %p"), "-", m.title)
    return 0


def cmd_signout():
    from meetreminder import gcal_api
    print("Signed out (token deleted)." if gcal_api.sign_out(BASE) else "Was not signed in.")
    print("To also revoke access at Google: https://myaccount.google.com/permissions")


def uninstall():
    try:
        startup_vbs().unlink()
        print("Removed auto-start.")
    except FileNotFoundError:
        print("Auto-start was not installed.")
    print("Stopped the running app." if ask_running_instance_to_quit() else "No running app found.")


class App:
    def __init__(self, demo=False, lock=None, demo_minutes=10.0):
        self.cfg = {**DEFAULT_CFG, **load_json(CONFIG, DEFAULT_CFG)}
        self.root = tk.Tk()
        self.root.withdraw()
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.need_auth = self.auth_warned = False
        if not demo:
            self.ensure_source()
        self.refresh_now = threading.Event()   # set => refresh the calendar immediately
        self.last_tick = time.time()
        self.sched = Scheduler(cancelled=set(load_json(STATE, {"cancelled": []}).get("cancelled", [])))
        self.meetings, self.popups, self.demo = [], {}, demo
        if demo:
            s = datetime.now(timezone.utc) + timedelta(minutes=demo_minutes)
            self.meetings = [Meeting("demo|" + s.isoformat(), "Sprint planning (demo)", s,
                                     s + timedelta(minutes=30), "https://meet.google.com/abc-defg-hij")]
        else:
            threading.Thread(target=self.refresh_loop, daemon=True).start()
        self.quit_flag = False
        if lock:
            threading.Thread(target=self.listen, args=(lock,), daemon=True).start()
        logging.info("started (demo=%s)", demo)
        self.tick()

    def ensure_source(self):
        """Make sure there is a working calendar source before the app starts."""
        if self.cfg["source"] == "notif":                    # temporary source, nothing to set up
            return
        if self.cfg["source"] == "ics":
            if not self.cfg["ics_url"]:
                self.ask_url()
            return
        try:
            from meetreminder import gcal_api
            if gcal_api.load_credentials(BASE) is None:          # first run: sign in via browser
                gcal_api.authorize(BASE, Path(__file__).resolve().parent)
        except ImportError:
            messagebox.showerror("Meet Reminder", "Google libraries are missing.\n\n"
                                 "Run: pip install -r requirements.txt")
            sys.exit(1)
        except FileNotFoundError as e:
            messagebox.showerror("Meet Reminder setup", str(e))
            sys.exit(1)
        except Exception as e:
            logging.exception("Google sign-in failed")
            messagebox.showerror("Meet Reminder", f"Google sign-in failed:\n{e}")
            sys.exit(1)

    def ask_url(self):
        url = simpledialog.askstring(
            "Meet Reminder setup",
            "Paste your Google Calendar 'Secret address in iCal format'\n"
            "(Calendar settings > your calendar > Integrate calendar):", parent=self.root)
        if not url:
            messagebox.showwarning("Meet Reminder", "No URL entered - exiting.")
            sys.exit(0)
        self.cfg["ics_url"] = url.strip()
        save_json(CONFIG, self.cfg)

    def refresh_loop(self):
        period = REFRESH_SECONDS
        if self.cfg["source"] == "notif":                   # TEMPORARY: Chrome Calendar pop-ups (notif_source.py)
            from meetreminder.notif_source import NotificationSource
            get = NotificationSource().poll
            auth_error, period = (), 15
        elif self.cfg["source"] == "ics":
            from meetreminder.calendar_source import fetch_ics, parse_meetings
            get = lambda: parse_meetings(fetch_ics(self.cfg["ics_url"]), only_meet=self.cfg["only_meet"],
                                         my_email=self.cfg["my_email"])
            auth_error = ()
        else:
            from meetreminder import gcal_api
            get = lambda: gcal_api.fetch_meetings(BASE, only_meet=self.cfg["only_meet"])
            auth_error = (gcal_api.AuthRequired,)
        fails = 0
        while True:
            try:
                self.meetings = get()
                logging.info("refreshed: %d upcoming meetings", len(self.meetings))
                fails, wait = 0, period
                self.need_auth = self.auth_warned = False
            except auth_error as e:                         # sign-in gone: ask the user once
                logging.error("%s", e)
                self.need_auth, wait = True, period
            except Exception as e:
                fails += 1
                if fails == 1:
                    logging.exception("calendar refresh failed (keeping previous data)")
                else:
                    logging.warning("calendar refresh failed again (%s)", e)
                wait = min(15 * 2 ** (fails - 1), 120)      # 15, 30, 60, 120 s ... (network may be down)
            self.refresh_now.wait(wait)                     # wakes early on resume from sleep
            self.refresh_now.clear()

    def persist(self):
        save_json(STATE, {"cancelled": sorted(self.sched.cancelled)[-500:]})

    def listen(self, lock):
        """A newer instance asks us to quit, so a stale copy can never block a new run."""
        while True:
            try:
                conn, _ = lock.accept()
                with conn:
                    conn.settimeout(2)
                    if conn.recv(16).strip() == b"quit":
                        logging.info("quit requested by a newer instance")
                        self.quit_flag = True
                        return
            except Exception:
                return

    def tick(self):
        if self.quit_flag:
            os._exit(0)
        t = time.time()
        if t - self.last_tick > 30:             # ticks are 1 s apart: a gap means sleep/hibernate
            logging.info("wake/resume detected (gap %.0f s): refreshing calendar now", t - self.last_tick)
            self.refresh_now.set()
        self.last_tick = t
        if self.need_auth and not self.auth_warned:         # Google sign-in expired/revoked
            self.auth_warned = True
            messagebox.showwarning("Meet Reminder", "Your Google sign-in expired or was revoked, so I "
                                   "can no longer read your calendar.\n\nRun:  python meet_reminder.py --auth")
        now = datetime.now(timezone.utc)
        try:
            self.popups = {k: p for k, p in self.popups.items() if p.alive}   # free closed ones
            meetings = list(self.meetings)
            for m, mins in self.sched.due(meetings, now):
                pop = self.popups.get(m.key)
                if pop and pop.alive:
                    pop.update_minutes(mins)           # same popup, new minute
                else:
                    from meetreminder.popup import Popup
                    self.popups[m.key] = Popup(self.root, m, mins, self.on_snooze,
                                               self.on_cancel, self.on_join)
                logging.info("reminder: %s in %d min", m.title, mins)
                self.beep()
            for k in self.sched.expired(meetings, now):
                p = self.popups.pop(k, None)
                if p and p.alive:
                    p.close()
        except Exception:
            logging.exception("tick failed")
            print("Meet Reminder error - see", LOG, file=sys.stderr)
        self.root.after(TICK_MS, self.tick)

    def beep(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def on_snooze(self, m):
        self.sched.snooze(m.key, datetime.now(timezone.utc))

    def on_cancel(self, m):
        self.sched.cancel(m.key); self.persist()

    on_join = on_cancel   # joining = no more reminders for that meeting

    def run(self):
        self.root.mainloop()


def ask_running_instance_to_quit():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=2) as c:
            c.sendall(b"quit")
        return True
    except OSError:
        return False


def single_instance(timeout=8):
    """Become the only instance. If one is already running, ask it to quit and take over."""
    deadline, asked = time.time() + timeout, False
    while True:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", PORT))
            s.listen(1)
            return s
        except OSError:
            s.close()
        if not asked:
            asked = ask_running_instance_to_quit()
        if time.time() > deadline:
            return None
        time.sleep(0.5)


if __name__ == "__main__":
    a = sys.argv[1:]
    BASE.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG, encoding="utf-8")]
    if sys.stderr is not None:                      # console run (python.exe), not pythonw
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")
    if "--install" in a:
        install()
    elif "--uninstall" in a:
        uninstall()
    elif "--auth" in a:
        sys.exit(cmd_auth())
    elif "--signout" in a:
        cmd_signout()
    elif "--status" in a:
        status()
    elif "--probe-notifications" in a:
        from meetreminder import notif_source
        notif_source.probe()
    elif "--start" in a or "--quickstart" in a:      # --quickstart = old name, still accepted
        quickstart()
    elif any(x.startswith("--source=") for x in a):
        v = next(x.split("=", 1)[1] for x in a if x.startswith("--source="))
        if v not in ("api", "notif", "ics"):
            sys.exit("--source must be api, notif or ics")
        cfg = {**DEFAULT_CFG, **load_json(CONFIG, {})}
        cfg["source"] = v
        save_json(CONFIG, cfg)
        print(f"Calendar source set to '{v}'. Restart with: python meet_reminder.py --install")
    elif "--stop" in a:                              # stop the app AND remove auto-start
        uninstall()
    else:
        lock = single_instance()
        if lock is None:
            logging.error("could not take over from an already running instance (old version?)")
            print("Another Meet Reminder is still running and did not respond. Stop it with:\n"
                  "  Get-CimInstance Win32_Process | Where CommandLine -like '*meet_reminder*' |"
                  " ForEach { Stop-Process -Id $_.ProcessId -Force }")
            sys.exit(1)
        dm = next((float(x.split("=", 1)[1]) for x in a if x.startswith("--demo-minutes=")), None)
        App(demo=("--demo" in a or dm is not None), lock=lock,
            demo_minutes=10.0 if dm is None else dm).run()
