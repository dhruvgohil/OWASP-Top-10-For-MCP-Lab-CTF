"""HelixSupport Session Signer -- a tiny internal token-minting microservice.

Runs on the private lab network only (no host port is published). Its job is to mint
HMAC-signed session tokens. The MCP server calls it during normal `authenticate` to issue
a token for a user's real role.

!!! THE CORE TRUST FLAW (MCP07) !!!
`/sign` mints a token for WHATEVER `role` the caller asks for, as long as they present the
`signing_key`. It performs no check that the requester is entitled to that role. Since the
key is leaked by the MCP server's verbose `status`, any user can obtain a `support` or
`admin` token here and then wield the MCP server's privileged tools. A real signer would
derive the role from an authenticated identity/session -- never from a client-supplied
field -- and would not treat a shared static secret as proof of authority.
"""

import os

from fastapi import FastAPI
from pydantic import BaseModel

import token_util

SIGNING_KEY = os.getenv("SIGNING_KEY", "helix-signing-key-2026")
TOKEN_TTL = int(os.getenv("TOKEN_TTL", "3600"))

app = FastAPI(title="HelixSupport Session Signer")


class SignRequest(BaseModel):
    signing_key: str
    user_id: str
    role: str = "user"
    ttl: int | None = None


@app.get("/health")
def health() -> dict:
    return {"service": "session-signer", "status": "ok"}


@app.post("/sign")
def sign(req: SignRequest) -> dict:
    # The ONLY gate is "do you know the shared signing key". The requested role is
    # trusted verbatim -- that is the vulnerability.
    if req.signing_key != SIGNING_KEY:
        return {"error": "invalid signing_key"}
    token = token_util.mint(req.user_id, req.role, SIGNING_KEY, req.ttl or TOKEN_TTL)
    return {"token": token, "user_id": req.user_id, "role": req.role}
