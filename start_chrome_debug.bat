@echo off
REM Launches your normal Chrome profile with remote debugging enabled so
REM bid_monitor.py can attach to it and reuse your existing Nellis Auction login.
REM
REM IMPORTANT: Close ALL Chrome windows first (check Task Manager for lingering
REM chrome.exe processes) — Chrome only opens the debug port if it was passed
REM at startup, not to an already-running instance.

set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_PATH% set CHROME_PATH="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

start "" %CHROME_PATH% --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data"

echo Chrome launched with remote debugging on port 9222.
echo Leave this Chrome window open, then run: python bid_monitor.py
pause
