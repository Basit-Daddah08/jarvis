@echo off
REM Installs ELION / JARVIS to run automatically in the background whenever Windows starts.
cd /d "%~dp0"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
copy /Y "%~dp0start_elion_background.vbs" "%STARTUP_DIR%\ELION_Background_Daemon.vbs" >nul
cscript //nologo "%~dp0start_elion_background.vbs"
echo ====================================================================
echo [SUCCESS] ELION Background Software is now running in the background
echo and registered to start automatically whenever you turn on your laptop.
echo Control Center: http://localhost:8080
echo ====================================================================
pause
