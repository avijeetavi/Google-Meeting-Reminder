@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" meet_reminder.py --status
echo.
pause
