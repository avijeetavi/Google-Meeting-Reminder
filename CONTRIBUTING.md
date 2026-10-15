# Contributing

Thanks for your interest in Meet Reminder! Changes are welcome through pull requests.

## How to propose a change

1. Fork this repository and create a branch for your change (`git checkout -b my-change`).
2. Make the change. Keep it small and focused: one fix or feature per pull request.
3. Run the tests from the project folder (no GUI needed):

   ```powershell
   python tests/test_scheduler.py
   python tests/test_scene.py
   python tests/test_gcal_api.py
   python tests/test_notif_source.py
   ```

4. Open a pull request that says what changed and why. Nothing is merged without the maintainer's review.

Direct pushes to `main` are not accepted; everything goes through a pull request.

## Ground rules

- **Never commit secrets or personal data:** no `client_secret.json`, `token.json`, `state.json`, `config.json`,
  logs, your calendar contents, or real meeting titles. Use made-up data in tests.
- **Keep it simple and local:** the app must not send calendar data anywhere except Google's own API when the
  Google Calendar API source is used. Do not add analytics or network calls.
- **Windows security tools:** do not add code that tries to bypass or hide from endpoint-security software.
- **Style:** match the existing code. Logic that does not need a window goes in the GUI-free modules
  (`meetreminder/scheduler.py`, `meetreminder/scene.py`, `meetreminder/gcal_api.py`) so it can be unit-tested.
- Update `README.md` if you change a command or behaviour.

## Reporting problems

Open an issue with your Windows version, Python version, the command you ran and the last lines of
`meet_reminder.log` (remove any meeting titles first).
