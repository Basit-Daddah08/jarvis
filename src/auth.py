import os
import secrets
import urllib.parse
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"

TOKEN_ENV_KEY = "ELION_AUTH_TOKEN"

def get_or_create_auth_token() -> str:
    """
    Retrieve ELION_AUTH_TOKEN from .env or environment.
    If not set or empty, generates a cryptographically secure 32-byte hex token (64 hex characters),
    persists it into .env, and returns it.
    """
    # 1. Check existing environment variable
    token = os.getenv(TOKEN_ENV_KEY, "").strip()
    if token:
        return token

    # 2. Check .env file on disk
    if ENV_PATH.exists():
        try:
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith(f"{TOKEN_ENV_KEY}="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        os.environ[TOKEN_ENV_KEY] = val
                        return val
        except Exception:
            pass

    # 3. Generate a new long random token (64 hex characters)
    new_token = secrets.token_hex(32)
    os.environ[TOKEN_ENV_KEY] = new_token

    # 4. Save to .env (creating or appending)
    try:
        if ENV_PATH.exists():
            existing = ENV_PATH.read_text(encoding="utf-8")
            if f"{TOKEN_ENV_KEY}=" in existing:
                lines = []
                for line in existing.splitlines():
                    if line.strip().startswith(f"{TOKEN_ENV_KEY}="):
                        lines.append(f"{TOKEN_ENV_KEY}={new_token}")
                    else:
                        lines.append(line)
                ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
            else:
                sep = "\n" if not existing.endswith("\n") else ""
                ENV_PATH.write_text(f"{existing}{sep}{TOKEN_ENV_KEY}={new_token}\n", encoding="utf-8")
        else:
            ENV_PATH.write_text(f"# ELION Environment Configuration\n{TOKEN_ENV_KEY}={new_token}\n", encoding="utf-8")
    except Exception as e:
        print(f"[auth] Notice: could not persist token to .env: {e}")

    return new_token

def verify_token(provided_token: Optional[str]) -> bool:
    """Securely compare provided token against expected ELION_AUTH_TOKEN using constant-time comparison."""
    if not provided_token:
        return False
    expected = get_or_create_auth_token()
    if not expected:
        return False
    return secrets.compare_digest(provided_token.strip(), expected.strip())

def extract_token_from_request(handler: Any, payload: Optional[dict] = None) -> Optional[str]:
    """
    Extract token from:
    1. Header 'X-Elion-Token'
    2. Header 'Authorization' ('Bearer <token>')
    3. URL query parameter '?token=...'
    4. JSON body payload {'token': '...'}
    """
    # 1. Custom Header
    header_token = handler.headers.get("X-Elion-Token") if hasattr(handler, "headers") else None
    if header_token and header_token.strip():
        return header_token.strip()

    # 2. Authorization Header
    auth_header = handler.headers.get("Authorization") if hasattr(handler, "headers") else None
    if auth_header:
        auth_header = auth_header.strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return token

    # 3. Query string '?token=...'
    if hasattr(handler, "path"):
        parsed = urllib.parse.urlparse(handler.path)
        qs = urllib.parse.parse_qs(parsed.query)
        token_params = qs.get("token", [])
        if token_params and token_params[0].strip():
            return token_params[0].strip()

    # 4. JSON body payload
    if payload and isinstance(payload, dict):
        body_token = payload.get("token")
        if body_token and str(body_token).strip():
            return str(body_token).strip()

    return None

def extract_and_verify_token(handler: Any, payload: Optional[dict] = None) -> bool:
    """Extract token from request headers, query string, or body, and verify it."""
    token = extract_token_from_request(handler, payload)
    return verify_token(token)
