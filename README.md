# Meet Reminder (Windows)

Background app that reminds you before your Google Calendar meetings (about 10 minutes before, then every minute
until the start). Before the start, a plane flies left to right across your whole screen on a random straight line,
towing a banner: countdown, meeting title, start time and **Snooze 5 min / Cancel** buttons. Hover the banner to
freeze it so the buttons are easy to click. With the Google Calendar API source it reminds only for Google Meet calls;
with the temporary Chrome pop-up source every event gets a reminder.

* **Cancel** - no more reminders for that meeting.
* **Snooze 5 min** - silent for 5 minutes, then reminders resume every minute. A snooze never delays the start
  alert: the moment the meeting starts, the "Meeting started" card appears, whatever the snooze says.
* **Meeting started** - no flight. A "Meeting started" card is fixed in the centre of the screen and blinks like a
  lamp (bright / dim) with a Cancel button, until you cancel it or 5 minutes after the start. Hovering keeps it lit.
* Only one copy ever runs. Cancel/Snooze close that meeting's popup, not the app.

---

## 1. One-time setup (after downloading the code)

The virtual environment (`.venv`) is **not** part of the repository: it is tied to one computer, so everyone creates
their own. It takes about a minute.

**Requirements:** Windows 10/11, Python 3.9 or newer from python.org (tick "Add python.exe to PATH" during install;
Tkinter is included), and Git if you clone instead of downloading the zip. Check with `python --version`.

**Step 1 - get the code** (PowerShell):

```powershell
git clone <repo-url> MeetReminder
cd MeetReminder
```

(Or download the zip from the repository page, unzip it, and `cd` into the folder.)

**Step 2 - create the virtual environment and install the dependencies** (run inside the project folder):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

You should now see `(.venv)` at the start of the prompt. Whenever you open a new PowerShell window, `cd` into the
folder and run `.\.venv\Scripts\Activate.ps1` again before the commands below.

* If PowerShell says scripts are disabled, do not change security settings. Skip activation and prefix every
  command with `.\.venv\Scripts\python.exe`, for example `.\.venv\Scripts\python.exe meet_reminder.py --demo`.
* To start over: delete the `.venv` folder and repeat step 2.

**Step 3 - try it** (no calendar needed):

```powershell
python meet_reminder.py --demo
```

A plane should fly across your screen. If it does, the installation is fine.

**Step 4 - choose where meetings come from** (pick one):

* **Official Google Calendar API (recommended):** follow `docs/GOOGLE_API_SETUP.md`. It needs a Google OAuth
  "Desktop app" client, which your IT/admin may have to create; save the `client_secret.json` they give you in
  `%APPDATA%\MeetReminder`, then sign in once (opens your browser, read-only access):

  ```powershell
  python meet_reminder.py --auth
  ```

* **Temporary, no admin needed - Chrome Calendar pop-ups (one command for everything):**

  ```powershell
  python meet_reminder.py --start
  ```

  It selects this source, checks that Windows' notification data is readable, installs auto-start and starts the
  app in the background. You can close PowerShell afterwards. Details in the last section of this file.

**Step 5 - Google API route only: run it in the background and start it at every login**
(the pop-up route already did this in step 4 with `--start`):

```powershell
python meet_reminder.py --install
```

Never make your calendar public and never share a secret calendar address.

## 2. Run it manually (works without any installer)

Run from the project folder, with the venv active (`(.venv)` in the prompt):

| What | Command |
|---|---|
| Preview the animation (fake meeting in 10 min) | `python meet_reminder.py --demo` |
| Preview the "Meeting started" banner | `python meet_reminder.py --demo-minutes=-1` |
| Run for real, in this terminal (keep the window open) | `python meet_reminder.py` |
| Run for real, no console window | `.\.venv\Scripts\pythonw.exe meet_reminder.py` |
| Check status (running? auto-start set up? last log lines) | `python meet_reminder.py --status` |
| Start in the background + auto-start at every sign-in | `python meet_reminder.py --start` |
| Stop the app and remove auto-start | `python meet_reminder.py --stop` |
| Sign in to Google Calendar (one time) and test-read 24 h | `python meet_reminder.py --auth` |
| Sign out (delete the saved token) | `python meet_reminder.py --signout` |

If you skipped `--auth`, the first real run starts the browser sign-in itself. Starting the app again replaces
a copy that is already running, so duplicates cannot pile up.

## 3. Double-click scripts (.bat) - optional

| File | Does the same as |
|---|---|
| `scripts\Start-MeetReminder.bat` | `--start` (starts in the background and sets up auto-start) |
| `scripts\Stop-MeetReminder.bat` | `--stop` (stops and removes auto-start) |
| `scripts\Status-MeetReminder.bat` | `--status` |

**Heads-up for managed (company) laptops:** the installer writes a hidden Startup entry and launches
a hidden process, which endpoint-security tools can treat as suspicious and may block (a `.bat` installer was
blocked this way on one managed laptop). If that happens, do not try to bypass it: use the
manual commands above, or ask IT/security to review and allow this folder. What the app does: reads your
own Google Calendar events (read-only API scope `calendar.events.readonly`, only talks to googleapis.com),
shows a local popup, writes `config.json`/`state.json`/`token.json` under `%APPDATA%\MeetReminder` and a log in
this folder; installs only `google-auth`, `google-auth-oauthlib` and `requests`.

## 4. Auto-start at sign-in (`--start` or `--install`; may be blocked, see above)

```powershell
python meet_reminder.py --start        # pop-up source: registers auto-start and starts now
python meet_reminder.py --install      # same, but keeps the chosen source (use after --source=api and --auth)
python meet_reminder.py --stop         # stops the running app AND removes auto-start 
```

It adds `MeetReminder.vbs` to `shell:startup` (Win+R). After restart/shutdown it starts at the next
sign-in. Sleep/hibernate keep it running; on wake it refreshes the calendar immediately and retries
quickly if the network is not back yet. Without auto-start, just run section 2 yourself after each boot.

## 4b. Stop it / remove it completely

| Goal | Command (PowerShell, in the project folder) |
|---|---|
| Start (also after you stopped it) | `python meet_reminder.py --start` |
| Stop the app AND remove auto-start | `python meet_reminder.py --stop` |
| Check the state | `python meet_reminder.py --status` (after `--stop`: "Running now: no" and auto-start "NOT installed") |
| Last resort if `--stop` finds nothing but a `pythonw.exe` is still running | see below |

After a restart nothing needs to be run: once `--start` has been used, the app starts by itself at every sign-in,
until you run `--stop`.

```powershell
Get-CimInstance Win32_Process | Where-Object CommandLine -like '*meet_reminder*' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

To also delete the saved settings and sign-in, remove the folder `%APPDATA%\MeetReminder` (paste it in the File Explorer
address bar). To sign out of Google only, use `python meet_reminder.py --signout`.

## 5. Tests (no GUI needed)

```powershell
python tests/test_scheduler.py
python tests/test_scene.py
```

## 6. Files and settings

* Layout: `meet_reminder.py` is the entry point and app (stays in the project root, so every command above is unchanged).
  `meetreminder/` holds the modules: `scheduler.py` timing rules, `gcal_api.py` Google Calendar API source,
  `notif_source.py` temporary Chrome pop-up source, `scene.py` plane +
  banner drawing and random routes, `popup.py` the full-screen animation window. `tests/` has the tests, `scripts/` the
  .bat helpers, `docs/` the setup guide.
* Tuning: `CRUISE_STEP` / `FAST_STEP` in `meetreminder/popup.py` (speed), `Scene.S` in `meetreminder/scene.py` (plane size),
  `VIOLET` / `CORAL` in `meetreminder/scene.py` (colours), `LEAD_MINUTES` / `SNOOZE_SECONDS` / `GRACE_SECONDS` in `meetreminder/scheduler.py`.

## 7. Troubleshooting

* **Nothing appears:** run `--status`, then read `meet_reminder.log`. Run `--demo` to test the animation
  without the calendar. The plane takes about 3 seconds to enter from the left edge.
* **No meetings found:** the event needs a Google Meet link and must not be all-day, cancelled or declined; run
  `--auth` (it prints what it can see) and check `only_meet` in `config.json`.
* **"Google sign-in expired" message:** run `python meet_reminder.py --auth` again.
* **"Access blocked" / "app is blocked" at sign-in:** your Google admin must allow the app - see `docs/GOOGLE_API_SETUP.md` section D.
* **Security tool blocked something:** see the heads-up in section 3.

## Temporary source: Chrome Calendar pop-ups (until the Google client secret arrives)

`meetreminder/notif_source.py` is a separate, optional file. It reads Google Calendar pop-ups that Chrome/Edge already
showed as Windows notifications (read-only; only calendar.google.com pop-ups are used, other apps' text is never
read or printed). Delete this file and its `notif` hooks once `client_secret.json` is available.

```
python meet_reminder.py --start            # ONE command: select it, check it, auto-start, run now
python meet_reminder.py --probe-notifications   # optional diagnostics (only if nothing shows up)
python meet_reminder.py --source=api            # go back to the official API (then --install)
```

Limits: it only learns about a meeting when Chrome shows its pop-up, so the 10-minute lead is not guaranteed;
the start time is estimated from the pop-up text ("in 5 minutes"). The Windows notification database layout and
the pop-up text format are unverified on your machine - run `--probe-notifications` first. If your security software flags
it, stop and ask IT; do not work around it.

## Contributing and licence

Pull requests are welcome - see `CONTRIBUTING.md`. Direct pushes to `main` are not accepted; changes are merged after
review. Released under the MIT licence (`LICENSE`).
