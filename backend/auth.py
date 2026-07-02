"""Single-admin session auth.

Tokens are random, kept in memory, and expire after SESSION_TTL_SECONDS.
Good enough for an internal MVP; a restart simply logs the admin out.
Image/stream endpoints accept the token as a ?token= query parameter
because <img> tags cannot send Authorization headers.
"""
import hmac
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request

from . import config

_sessions: dict[str, float] = {}  # token -> expiry timestamp


def login(username: str, password: str) -> Optional[str]:
    user_ok = hmac.compare_digest(username, config.ADMIN_USERNAME)
    pass_ok = hmac.compare_digest(password, config.ADMIN_PASSWORD)
    if not (user_ok and pass_ok):
        return None
    token = secrets.token_hex(24)
    _sessions[token] = time.time() + config.SESSION_TTL_SECONDS
    return token


def logout(token: str) -> None:
    _sessions.pop(token, None)


def _valid(token: Optional[str]) -> bool:
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None:
        return False
    if expiry < time.time():
        _sessions.pop(token, None)
        return False
    return True


def _extract_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token")


async def require_auth(request: Request) -> str:
    token = _extract_token(request)
    if not _valid(token):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token


AuthDep = Depends(require_auth)
