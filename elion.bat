@echo off
setlocal
cd /d "%~dp0"

REM Check for venv python
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_CMD=python"
    ) else (
        echo [ERROR] Virtual environment .venv not found. Run setup.bat first.
        exit /b 1
    )
)

%PYTHON_CMD% src\launcher.py %*
