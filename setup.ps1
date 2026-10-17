# ELION (JARVIS) — Automated Environment Setup (PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ELION (JARVIS) — Automated Environment Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Locate Python
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonCmd) {
    $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (-not $pythonCmd) {
    Write-Error "[ERROR] Python is not installed or not found in PATH."
    exit 1
}

Write-Host "[*] Found Python: $pythonCmd"

# 2. Create virtual environment
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[*] Creating virtual environment in .venv..."
    & $pythonCmd -m venv .venv
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[*] Virtual environment .venv already exists."
}

$venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"

# 3. Upgrade pip
Write-Host "[*] Upgrading pip in .venv..."
& $venvPython -m pip install --upgrade pip --quiet

# 4. Install requirements
Write-Host "[*] Installing pinned requirements from requirements.txt..."
& $venvPython -m pip install -r requirements.txt
Write-Host "[OK] Dependencies installed." -ForegroundColor Green

# 5. Initialize .env and token
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[*] Created .env from template."
}

Write-Host "[*] Initializing security token in .env..."
& $venvPython -c 'from src.auth import get_or_create_auth_token; tok = get_or_create_auth_token(); print("[OK] Auth Token configured: " + tok[:8] + "..." + tok[-4:])'

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "To activate the environment:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "To start the ELION server:"
Write-Host "  .\.venv\Scripts\python.exe src\dashboard\serve.py"
Write-Host "============================================================" -ForegroundColor Cyan
