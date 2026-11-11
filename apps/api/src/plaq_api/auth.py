"""API-key resolution for Plaq-OS.

Auth is on by default for real servers:
- ``PLAQ_API_KEY`` wins if set
- otherwise a key is loaded or generated next to the control-plane DB
  (``~/.plaq/api_key`` or ``$PLAQ_DB_PATH/../api_key``)
- ``PLAQ_AUTH=off`` disables auth (local docker / explicit opt-out)
- pytest runs stay open so the existing test suite does not need keys
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import sys
from typing import Optional, Tuple


def _running_under_pytest() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def default_key_path() -> Path:
    env_db = os.environ.get("PLAQ_DB_PATH", "").strip()
    if env_db:
        return Path(env_db).expanduser().resolve().parent / "api_key"
    return Path.home() / ".plaq" / "api_key"


def _auth_flag() -> str:
    return os.environ.get("PLAQ_AUTH", "").strip().lower()


def resolve_api_key(generate: bool = True) -> Optional[str]:
    """Return the Bearer token the API should require, or None if auth is off."""
    flag = _auth_flag()
    if flag in {"off", "0", "false", "optional", "disabled"}:
        return None
    env_key = os.environ.get("PLAQ_API_KEY", "").strip()
    if env_key:
        return env_key
    if _running_under_pytest():
        return None
    path = default_key_path()
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    if not generate:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    key = "plaq_" + secrets.token_urlsafe(24)
    path.write_text(key + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def is_authorized(api_key: str, authorization: str = "", cookie: str = "", query_token: str = "") -> bool:
    """True if Bearer, session cookie, or ``?token=`` matches ``api_key``."""
    if not api_key:
        return True
    bearer = ""
    if authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    for candidate in (bearer, cookie, query_token):
        if candidate and secrets.compare_digest(candidate, api_key):
            return True
    return False


SESSION_COOKIE = "plaq_session"


def describe_auth() -> Tuple[Optional[str], str]:
    """Return (key, human message) for CLI / server banners."""
    key = resolve_api_key(generate=True)
    if not key:
        return None, "API auth is OFF (PLAQ_AUTH=off). /api/v1/* is open."
    path = default_key_path()
    msg = (
        "API auth is ON. Send header: Authorization: Bearer <key>\n"
        f"  Key file: {path}"
    )
    return key, msg
