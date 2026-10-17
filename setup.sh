#!/usr/bin/env bash
set -e

echo "============================================================"
echo "  ELION (JARVIS) — Automated Environment Setup"
echo "============================================================"

# 1. Check Python
PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" &>/dev/null; then
    PYTHON_CMD="python"
fi

if ! command -v "$PYTHON_CMD" &>/dev/null; then
    echo "[ERROR] Python 3 not found in PATH."
    exit 1
fi

echo "[*] Using Python: $($PYTHON_CMD --version)"

# 2. Create venv
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    "$PYTHON_CMD" -m venv .venv
    echo "[OK] Virtual environment created."
else
    echo "[*] Virtual environment (.venv) already exists."
fi

# 3. Upgrade pip and install
echo "[*] Upgrading pip..."
.venv/bin/python -m pip install --upgrade pip --quiet

echo "[*] Installing dependencies from requirements.txt..."
.venv/bin/python -m pip install -r requirements.txt

# 4. Initialize .env with auth token
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[*] Created .env from template."
fi

echo "[*] Initializing security token in .env..."
.venv/bin/python -c "from src.auth import get_or_create_auth_token; tok = get_or_create_auth_token(); print('[OK] Auth Token configured: ' + tok[:8] + '...' + tok[-4:])"

echo "============================================================"
echo "  Setup Complete!"
echo "============================================================"
echo "Activate: source .venv/bin/activate"
echo "Start:    python src/dashboard/serve.py"
echo "============================================================"
