@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo   ELION (JARVIS) — Enable Auto-Start on Windows Login
echo ============================================================
echo.
call elion.bat autostart enable
echo.
echo Starting ELION in the background now...
cscript //nologo start_elion_background.vbs
echo.
call elion.bat status
echo.
pause
