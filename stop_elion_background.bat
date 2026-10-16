@echo off
REM Stops the ELION background daemon if running
cd /d "%~dp0"
if exist "state\daemon.pid" (
    set /p DAEMON_PID=<state\daemon.pid
    taskkill /PID %DAEMON_PID% /F 2>nul
    del /F /Q "state\daemon.pid" 2>nul
    echo [STOPPED] ELION background daemon stopped.
) else (
    echo ELION background daemon is not currently running via PID file.
)
pause
