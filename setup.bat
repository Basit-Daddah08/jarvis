@echo off
setlocal

echo ============================================================
echo   ELION (JARVIS) -- Automated Environment Setup
echo ============================================================

REM 1. Check for Python
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_CMD=py -3"
    ) else (
        echo [ERROR] Python is not installed or not in PATH.
        echo Please install Python 3.10+ and re-run this setup script.
        pause
        exit /b 1
    )
)

echo [*] Using Python: %PYTHON_CMD%

REM 2. Create virtual environment .venv if it does not exist
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment in .venv...
    %PYTHON_CMD% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [*] Virtual environment .venv already exists.
)

REM 3. Upgrade pip
echo [*] Upgrading pip in .venv...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet

REM 4. Install pinned requirements
echo [*] Installing pinned dependencies from requirements.txt...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)
echo [OK] Dependencies installed successfully.

REM 5. Initialize .env and generate long random ELION_AUTH_TOKEN
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [*] Created .env from .env.example template.
    )
)

echo [*] Initializing security token in .env...
.venv\Scripts\python.exe -c "from src.auth import get_or_create_auth_token; tok = get_or_create_auth_token(); print('[OK] Auth Token configured: ' + tok[:8])"

echo ============================================================
echo   Setup Complete!
echo ============================================================
echo To activate the virtual environment:
echo   .venv\Scripts\activate
echo.
echo To start the ELION daemon and dashboard:
echo   .venv\Scripts\python src\dashboard\serve.py
echo ============================================================
