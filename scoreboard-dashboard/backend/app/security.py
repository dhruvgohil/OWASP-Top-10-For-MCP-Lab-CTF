"""Auth primitives: password hashing, session tokens, signed cookies, CSRF.

Design goals:
- Passwords: bcrypt (per-password salt) via passlib. Plaintext is never stored.
- Sessions: opaque 256-bit tokens stored server-side, handed to the client only
  inside a *signed* httpOnly cookie. The signature stops cookie forgery; the
  httpOnly flag stops XSS from reading it.
- CSRF: a double-submit token bound to the session, required on every
  state-changing request.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext

from . import config
from .timeutil import utcnow

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_signer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="helix-sb-session")


# --- Passwords ---------------------------------------------------------------


def hash_password(plaintext: str) -> str:
    return _pwd.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plaintext, hashed)
    except ValueError:
        return False


# --- Tokens ------------------------------------------------------------------


def new_session_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry() -> datetime:
    return utcnow() + timedelta(seconds=config.SESSION_TTL_SECONDS)


# --- Signed cookie transport -------------------------------------------------


def sign_cookie(session_token: str) -> str:
    """Wrap the opaque session token in a tamper-evident signed string."""
    return _signer.dumps(session_token)


def unsign_cookie(cookie_value: str) -> str | None:
    """Return the session token if the signature is valid and unexpired."""
    try:
        return _signer.loads(cookie_value, max_age=config.SESSION_TTL_SECONDS)
    except BadSignature:
        return None
    except Exception:
        return None


# --- Constant-time comparisons ----------------------------------------------


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
