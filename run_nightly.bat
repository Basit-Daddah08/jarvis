@echo off
REM JARVIS Nightly Runner Script
REM Scheduled via Windows Task Scheduler or run manually

cd /d "%~dp0"
echo ======================================================
echo Starting JARVIS Overnight Review...
echo ======================================================

python src\run.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] JARVIS pipeline encountered an issue.
) else (
    echo [SUCCESS] Nightly review finished. Vault and INBOX updated.
)
