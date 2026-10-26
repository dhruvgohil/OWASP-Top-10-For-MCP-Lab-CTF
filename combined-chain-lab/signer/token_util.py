"""Tiny HMAC-signed session tokens shared by the MCP server and the signer service.

A token is a JWT-ish blob:

    b64url(json{"user_id":..., "role":..., "exp":...}) + "." + HMAC_SHA256(SIGNING_KEY, body)

Both the Support MCP server and the standalone Session Signer import THIS SAME file and
share one `SIGNING_KEY` (via env), so a token minted by either is accepted by the other.

TEACHING NOTE (MCP07): verification here proves only that *someone who holds the signing
key* produced the token. It does NOT prove the embedded `role` claim was legitimately
granted. The signer will happily sign `role="support"` or `role="admin"` for anyone who
presents the key -- and the key is leaked by the `status(verbose=True)` tool. That broken
trust boundary is the heart of the privilege-escalation objective.
"""

import base64
import hashlib
import hmac
import json
import time


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sign_token(payload: dict, signing_key: str) -> str:
    """Serialize + HMAC-sign a payload into a session token string."""
    body = _b64url(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    sig = hmac.new(signing_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def mint(user_id: str, role: str, signing_key: str, ttl_seconds: int = 3600) -> str:
    """Convenience: build + sign a token for (user_id, role) with a TTL."""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": int(time.time()) + int(ttl_seconds),
    }
    return sign_token(payload, signing_key)


def verify_token(token: str, signing_key: str) -> dict | None:
    """Return the payload dict if the token is valid and unexpired, else None.

    Trusts whatever `role` the payload carries -- see the module docstring.
    """
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    expected = hmac.new(
        signing_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(body))
    except Exception:  # noqa: BLE001 - malformed token -> treat as invalid
        return None
    exp = payload.get("exp")
    if exp is not None and time.time() > float(exp):
        return None
    return payload
