# Google Calendar API setup (one time, about 10 minutes)

Why: the "Secret address in iCal format" is hidden on some company Google accounts (and the
"Public address" only works if the calendar is made public - never do that). So the app reads the
calendar through the **official Google Calendar API**, read-only.

What the app is allowed to do: scope `calendar.events.readonly` = **read events only**. It cannot
create, edit or delete anything, and it cannot read mail, Drive, contacts, etc.

You need an "OAuth client" (a Desktop-app credential) from a Google Cloud project. Google's console
labels change now and then; the steps below describe the intent.

## A. Create the OAuth client
1. Open <https://console.cloud.google.com/> signed in with your work account. Create a project
   (e.g. "Meet Reminder") - or use an existing project you are allowed to use.
   *If you cannot create projects, ask IT (see section D).*
2. **APIs & Services > Library** > search **Google Calendar API** > **Enable**.
3. **OAuth consent screen** (newer console: **Google Auth Platform**):
   * Audience / user type: **Internal** (only people in your Workspace organisation, no Google
     verification needed). If only "External" is offered, stop and ask IT.
   * App name e.g. "Meet Reminder", support email = your work email.
   * Data access / scopes: add `.../auth/calendar.events.readonly` (View events on all your calendars).
4. **Credentials > Create credentials > OAuth client ID** > Application type **Desktop app** > Create >
   **Download JSON**.
5. Save the downloaded file as **`%APPDATA%\MeetReminder\client_secret.json`**
   (paste `%APPDATA%\MeetReminder` into the File Explorer address bar; create the folder if needed).
   Do not put it in a shared folder, chat, ticket or Git repo.

## B. Sign in once
```powershell
cd C:\Users\<username>\Downloads\MeetReminder
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python meet_reminder.py --auth
```
Your browser opens > choose your work account > **Allow**. The terminal then prints the Meet meetings
it found in the next 24 hours. After that, `python meet_reminder.py` just runs (no browser).

## C. Manage / undo
* Sign out of the app: `python meet_reminder.py --signout` (deletes `%APPDATA%\MeetReminder\token.json`).
* Revoke at Google: <https://myaccount.google.com/permissions> > Meet Reminder > Remove access.
* `token.json` holds a long-lived refresh token for **read-only calendar events**. It lives only in your
  Windows profile; treat it like a password.
* If Google signs you out (password change, admin action) the app shows a message: run `--auth` again.

## D. If it is blocked - message for IT / Google Workspace admin
> I'm running a small local app (Meet Reminder) that shows an on-screen reminder before my Google Meet
> calls. It needs Google Calendar API access, read-only (`calendar.events.readonly`), for my own account.
> Could you (1) allow me to create a Google Cloud project / Desktop OAuth client, or provide an approved
> one, and (2) allow it under API controls if third-party apps are restricted? Data stays on my laptop;
> it only talks to googleapis.com. Source is a few plain Python files I can share for review.

Typical errors: **"Access blocked: ... admin policy"** or **"app is blocked"** = the admin must allow the app;
**"This app isn't verified"** = the consent screen is External, switch to Internal or ask IT.
