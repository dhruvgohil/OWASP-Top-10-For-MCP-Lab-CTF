"""Vulnerable "HelixSupport" help-desk MCP server (COMBINED CHAIN LAB).

An intentionally-vulnerable, fully-local help-desk exposed as MCP tools over the modern
Streamable HTTP transport, reachable by the backend container at
http://mcp-server:8001/mcp.

This is the target for a SEQUENTIAL, staged security lab that chains three OWASP MCP
weaknesses into one kill-chain. Each stage's authorization tier gates the next, so no flag
can be captured out of order:

  1. INFO DISCLOSURE   - `status(verbose=True)` leaks the internal service map, the
                         `SIGNING_KEY`, and FLAG 1 to anyone, unauthenticated.        (MCP07)
  2. BROKEN TRUST      - tokens are accepted purely on HMAC validity; the embedded `role`
                         claim is trusted. The signer signs ANY role for anyone holding the
                         (leaked) key -> mint `support` then `admin` at will.          (MCP07)
  3. BOLA ON WRITE     - `get_ticket` enforces ticket ownership, but `add_note` does NOT.
                         Any authenticated user can append notes to ANY ticket -- including
                         the ADMIN's own ticket (its number varies per player/tenant; find it
                         via support-tier list_tickets). A confused-deputy support agent then
                         resolves it and resets the admin account, disclosing FLAG 3 and the
                         new admin password -> authenticate as admin.                  (MCP07)
  4. NO OBJECT AUTHZ   - `reset_password` / `update_customer` act on ANY target.
  5. SSRF/DEPUTY VECTOR- `call_internal_service` lets a low-priv user drive server-side
                         requests to internal URLs (e.g. the leaked SIGNER_URL).
  6. COMMAND INJECTION - the ADMIN-only `create_issue` builds an OS shell command out of the
                         untrusted issue *title* and runs it with `subprocess(shell=True)`
                         (CWE-78 / CVE-2026-0756 class). Reachable only once you hold an
                         admin token from stage 3. Reads `/root/flag.txt` -> FLAG 4. (MCP05)

None of these require the LLM to misbehave. Fix the authorization decisions (and the shell
sink) and re-run the same prompts: the chain falls apart.
"""

import os
import subprocess
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

import token_util
from board_store import BoardStore, BoardError
from support_store import SupportStore, StoreError

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8001"))
DATA_ROOT = os.getenv("DATA_ROOT", "/data/support")
BOARD_ROOT = os.getenv("BOARD_ROOT", "/data/board")
ACTIVITY_LOG = os.path.join(BOARD_ROOT, "activity.log")

SIGNING_KEY = os.getenv("SIGNING_KEY", "helix-signing-key-2026")
SIGNER_URL = os.getenv("SIGNER_URL", "http://signer:9003/sign")
# Session-token lifetime for the local-fallback mint (the signer path uses the signer's own
# TOKEN_TTL). Generous so a human-paced multi-stage solve never expires a token mid-chain.
TOKEN_TTL = int(os.getenv("TOKEN_TTL", "7200"))

# The staged objectives. FLAG 1 leaks from verbose status; FLAG 2 from env_debug (support
# tier); FLAG 3 is the ADMIN account's recovery code, seeded into the store and surfaced by
# resetting that account. FLAG 4 is NOT referenced anywhere in this process -- it lives ONLY
# in /root/flag.txt inside this container and is reachable solely by executing a command
# through the vulnerable admin-tier create_issue tool.
FLAG1 = os.getenv("FLAG1", "FLAG{CHAIN_STATUS_INFO_DISCLOSURE}")
FLAG2 = os.getenv("FLAG2", "FLAG{CHAIN_SIGNER_PRIVILEGE_ESCALATION}")
FLAG3 = os.getenv("FLAG3", "FLAG{CHAIN_ADMIN_BOLA_CONFUSED_DEPUTY}")

# Internal microservice map -- mimics otto-support's localhost service split. Only the
# signer actually runs in this lab; the rest exist to make the leaked config look real.
SERVICE_MAP = {
    "metadata": "http://metadata:9001",
    "customer_api": "http://customer:9002",
    "session_signer": SIGNER_URL,
    "payment_gateway": "http://payment:9004",
}

mcp = FastMCP("helixsupport", host=HOST, port=PORT)

# ======================================================================================
# Per-participant (tenant) isolation
#
# This lab runs as ONE set of containers but is shared by many CTF players simultaneously.
# Each browser sends a STABLE `X-Helix-Tenant` header (plumbed through the backend from the
# frontend's localStorage id). We keep a SEPARATE data partition per tenant -- its own
# SupportStore/BoardStore rooted under a per-tenant directory -- so one player's poisoned
# note, admin-password reset, signups, and board issues never touch another player's world.
# Concurrent admin resets land in different files, so they are inherently independent.
#
# No `X-Helix-Tenant` header -> tenant "default" -> the original single-player behavior
# (direct MCP testing and the /api/health tool probe keep working). This changes NO tool
# signature, so every exploit prompt in the walkthrough is byte-for-byte unaffected.
# ======================================================================================
_STORES: dict[str, SupportStore] = {}
_BOARDS: dict[str, BoardStore] = {}


def _tenant() -> str:
    """Resolve the current request's tenant from the X-Helix-Tenant header (default-safe).

    On the SDK's FastMCP (mcp>=1.2,<2), the per-request Starlette Request is reachable as
    ``mcp.get_context().request_context.request`` on HTTP transports. We read it defensively:
    any missing attribute / absent request context falls back to the single "default" tenant
    (import time, non-HTTP transports, or an SDK build without a request handle) so the server
    never crashes -- it just degrades to shared behavior, which the verification step checks for.
    """
    try:
        rc = mcp.get_context().request_context
        req = getattr(rc, "request", None)
        headers = getattr(req, "headers", None)
        if headers is not None:
            val = headers.get("x-helix-tenant")
            if val:
                return val
    except Exception:  # noqa: BLE001 - no HTTP request context -> single "default" tenant
        pass
    return "default"


def _seed_board_if_empty(board: BoardStore) -> None:
    if board.is_empty():
        board.add_issue("Set up CI pipeline", "Configure build-and-test for the platform repo.", "devops,infra")
        board.add_issue("Rotate TLS certificates", "Quarterly cert rotation for the edge nodes.", "security,infra")
        board.move(1, "In Progress")


def _current_store() -> SupportStore:
    """The calling tenant's help-desk store, lazily created and seeded on first use."""
    tenant = _tenant()
    st = _STORES.get(tenant)
    if st is None:
        st = SupportStore(os.path.join(DATA_ROOT, tenant), victim_recovery_code=FLAG3)
        _STORES[tenant] = st
    return st


def _current_board() -> BoardStore:
    """The calling tenant's engineering project board, lazily created and seeded on first use.

    Pure-Python persistence (no git, no shell) -- the ONLY shell in this whole server is the
    create_issue notification hook below.
    """
    tenant = _tenant()
    bd = _BOARDS.get(tenant)
    if bd is None:
        bd = BoardStore(os.path.join(BOARD_ROOT, tenant))
        _seed_board_if_empty(bd)
        _BOARDS[tenant] = bd
    return bd


# ======================================================================================
# Authorization helpers  (this is where MCP07 is won or lost)
# ======================================================================================

def _identity(token: str) -> dict | None:
    """Resolve a session token to its claims, or None if invalid/expired.

    NOTE: this only checks the HMAC signature + expiry. It does NOT and CANNOT tell
    whether the `role` was legitimately issued -- a forged support token minted through
    the leaked signing key verifies exactly like a real one.
    """
    return token_util.verify_token(token, SIGNING_KEY)


def _deny(message: str, claims: dict | None = None) -> dict:
    out = {"error": message}
    if claims is not None:
        out["your_role"] = claims.get("role")
        out["your_user_id"] = claims.get("user_id")
    return out


def _require_role(token: str, allowed: set[str]) -> tuple[dict | None, dict | None]:
    """Return (claims, None) if authorized, else (None, error_dict).

    Function-level authorization: gate a tool behind a set of roles. The gap the lab
    exploits is not *this* check -- it is that the roles it trusts can be forged.
    """
    claims = _identity(token)
    if not claims:
        return None, _deny("Not authenticated: missing or invalid session token.")
    if claims.get("role") not in allowed:
        return None, _deny(
            f"Not authorized: this action requires one of {sorted(allowed)}.", claims
        )
    return claims, None


# ======================================================================================
# PUBLIC TIER  (no authentication required)
# ======================================================================================

@mcp.tool()
def status(verbose: bool = False) -> dict:
    """Report service health.

    Args:
        verbose: If true, include detailed diagnostics for support engineers.
    """
    basic = {
        "service": "HelixSupport",
        "status": "operational",
        "version": "3.4.1",
        "tools": "public/user/support/admin tiers available",
    }
    if not verbose:
        return basic

    # !!! VULNERABLE (info disclosure) !!!
    # "Verbose" diagnostics dump the internal service topology AND the session signing
    # key to ANY caller, authenticated or not. In a real system this belongs behind an
    # admin-only, redacted diagnostics endpoint -- never in a public health check.
    basic["diagnostics"] = {
        "internal_services": SERVICE_MAP,
        "session_signer_url": SIGNER_URL,
        "signing_key": SIGNING_KEY,
        "token_algorithm": "HMAC-SHA256 over b64url(json).sig",
        "note": "signer mints a session token for any user_id/role given the signing_key",
        "build_flag": FLAG1,
    }
    return basic


@mcp.tool()
def create_user(username: str, email: str = "") -> dict:
    """Self-service signup. Creates a customer account and returns its credentials.

    Args:
        username: Desired account username.
        email: Optional contact email.
    """
    try:
        user = _current_store().create_user(username, email)
    except StoreError as exc:
        return {"error": str(exc)}
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "password": user["password"],
        "email": user["email"],
        "role": user["role"],
        "note": "Save these credentials, then call authenticate(username, password).",
    }


@mcp.tool()
def authenticate(username: str, password: str) -> dict:
    """Authenticate with username + password and receive a session token.

    Args:
        username: Account username.
        password: Account password (returned at signup).
    """
    user = _current_store().check_password(username, password)
    if not user:
        return {"error": "Authentication failed: unknown username or wrong password."}

    # Benign path: mint a token for the user's REAL role via the signer service. (If the
    # signer is briefly unreachable we fall back to a local mint so the lab still runs.)
    token = None
    try:
        with httpx.Client(timeout=8.0) as http:
            resp = http.post(
                SIGNER_URL,
                json={"signing_key": SIGNING_KEY, "user_id": user["user_id"], "role": user["role"]},
            )
            if resp.status_code == 200:
                token = resp.json().get("token")
    except Exception:  # noqa: BLE001 - signer optional; degrade gracefully
        token = None
    if not token:
        token = token_util.mint(user["user_id"], user["role"], SIGNING_KEY, TOKEN_TTL)

    return {
        "authenticated": True,
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "session_token": token,
        "note": "Pass session_token to authenticated tools.",
    }


# ======================================================================================
# USER TIER  (any authenticated caller)
# ======================================================================================

@mcp.tool()
def create_ticket(token: str, subject: str, body: str = "") -> dict:
    """Open a new support ticket owned by the authenticated caller.

    Args:
        token: Your session token.
        subject: Short ticket subject.
        body: Description of the issue.
    """
    claims = _identity(token)
    if not claims:
        return _deny("Not authenticated: missing or invalid session token.")
    owner = _current_store().get_user(claims["user_id"])
    if not owner:
        return _deny("Session refers to an unknown user.", claims)
    ticket = _current_store().create_ticket(owner, subject, body)
    return {
        "ticket_id": ticket["ticket_id"],
        "subject": ticket["subject"],
        "status": ticket["status"],
        "owner": ticket["owner_username"],
    }


@mcp.tool()
def list_tickets(token: str) -> dict:
    """List the authenticated caller's own tickets.

    Args:
        token: Your session token.
    """
    claims = _identity(token)
    if not claims:
        return _deny("Not authenticated: missing or invalid session token.")
    # Support/admin see the whole queue (a legitimate support capability); regular users
    # see only their own tickets.
    if claims.get("role") in {"support", "admin"}:
        return {"scope": "all", "tickets": _current_store().list_all_tickets()}
    return {"scope": "own", "tickets": _current_store().list_tickets_for(claims["user_id"])}


@mcp.tool()
def get_ticket(token: str, ticket_id: int) -> dict:
    """Read a ticket, including its notes.

    Args:
        token: Your session token.
        ticket_id: The ticket number to read.
    """
    claims = _identity(token)
    if not claims:
        return _deny("Not authenticated: missing or invalid session token.")
    try:
        ticket = _current_store().get_ticket(int(ticket_id))
    except StoreError as exc:
        return {"error": str(exc)}

    # Object-level authorization on READ *is* enforced: a regular user may only read a
    # ticket they own. Support/admin may read any ticket. (Contrast with add_note below,
    # where this very check is missing -- that asymmetry is the BOLA objective.)
    if claims.get("role") not in {"support", "admin"} and ticket["owner_id"] != claims["user_id"]:
        return _deny(
            f"Not authorized: ticket #{ticket_id} belongs to another customer.", claims
        )
    return ticket


@mcp.tool()
def add_note(token: str, ticket_id: int, note: str) -> dict:
    """Append a note to a ticket.

    Args:
        token: Your session token.
        ticket_id: The ticket number to append to.
        note: The note text.
    """
    claims = _identity(token)
    if not claims:
        return _deny("Not authenticated: missing or invalid session token.")
    try:
        ticket = _current_store().get_ticket(int(ticket_id))
    except StoreError as exc:
        return {"error": str(exc)}

    # !!! VULNERABLE (BOLA / IDOR on write) !!!
    # We authenticated the caller but NEVER check that this ticket is theirs. Any logged-in
    # user can append notes to ANY ticket by number -- including another customer's ticket.
    # The correct fix mirrors get_ticket's ownership check:
    #     if claims["role"] not in {"support","admin"} and ticket["owner_id"] != claims["user_id"]:
    #         return _deny(...)
    author = claims.get("user_id", "unknown")
    user = _current_store().get_user(author)
    if user:
        author = user["username"]
    updated = _current_store().add_note(int(ticket_id), author, note)
    cross_owner = ticket["owner_id"] != claims.get("user_id")
    return {
        "ticket_id": updated["ticket_id"],
        "owner": updated["owner_username"],
        "notes": len(updated["notes"]),
        "note_added_by": author,
        "wrote_to_other_users_ticket": cross_owner,
    }


@mcp.tool()
def call_internal_service(token: str, url: str, json_body: dict | None = None) -> dict:
    """Call an internal HelixSupport microservice and return its response.

    A diagnostics/integration helper for wiring up internal services.

    Args:
        token: Your session token.
        url: Internal service URL to POST to.
        json_body: JSON payload to send.
    """
    claims = _identity(token)
    if not claims:
        return _deny("Not authenticated: missing or invalid session token.")

    # !!! VULNERABLE (confused-deputy / SSRF vector) !!!
    # Any authenticated caller can make the SERVER issue an arbitrary internal request.
    # Combined with the SIGNER_URL + SIGNING_KEY leaked by verbose status, a low-priv user
    # drives the server into minting a privileged token on their behalf. A real system
    # would not expose a generic outbound-request tool to customers at all.
    if not str(url).lower().startswith(("http://", "https://")):
        return {"error": "url must be an http(s) URL."}
    try:
        with httpx.Client(timeout=8.0) as http:
            resp = http.post(url, json=json_body or {})
            try:
                payload = resp.json()
            except Exception:  # noqa: BLE001
                payload = resp.text
            return {"status_code": resp.status_code, "response": payload}
    except Exception as exc:  # noqa: BLE001 - surface network errors to the caller
        return {"error": f"request to {url} failed: {exc}"}


# ======================================================================================
# SUPPORT TIER  (role in {support, admin})
# ======================================================================================

@mcp.tool()
def search_customers(token: str, query: str = "") -> dict:
    """Search customer accounts by username, email, or company.

    Args:
        token: Your session token (support role or higher).
        query: Substring to match; empty returns all customers.
    """
    claims, err = _require_role(token, {"support", "admin"})
    if err:
        return err
    return {"query": query, "customers": _current_store().search_users(query)}


@mcp.tool()
def update_customer(token: str, user_id: str, email: str = "", plan: str = "", company: str = "") -> dict:
    """Update a customer's profile fields.

    Args:
        token: Your session token (support role or higher).
        user_id: The customer to update.
        email: New email (optional).
        plan: New plan (optional).
        company: New company (optional).
    """
    claims, err = _require_role(token, {"support", "admin"})
    if err:
        return err
    fields = {k: v for k, v in {"email": email, "plan": plan, "company": company}.items() if v}
    # !!! NO OBJECT AUTHZ: acts on ANY user_id, unrelated to the caller. !!!
    try:
        return {"updated": _current_store().update_user(user_id, fields)}
    except StoreError as exc:
        return {"error": str(exc)}


@mcp.tool()
def reset_password(token: str, user_id: str, new_password: str = "") -> dict:
    """Reset a customer's password and return their account recovery details.

    Args:
        token: Your session token (support role or higher).
        user_id: The customer whose password to reset.
        new_password: New password; if omitted, a random one is generated.
    """
    claims, err = _require_role(token, {"support", "admin"})
    if err:
        return err
    # !!! NO OBJECT AUTHZ: resets ANY account, and the response discloses the recovery
    # code -- so resetting the victim (usr_john) surfaces FLAG 3. !!!
    try:
        return {"reset": _current_store().reset_password(user_id, new_password)}
    except StoreError as exc:
        return {"error": str(exc)}


@mcp.tool()
def env_debug(token: str) -> dict:
    """Dump the running service configuration for support debugging.

    Args:
        token: Your session token (support role or higher).
    """
    claims, err = _require_role(token, {"support", "admin"})
    if err:
        return err
    # Support-tier config dump. Leaks the signing key again and carries FLAG 2 -- reaching
    # this at all proves the function-level authz bypass via the forged support token.
    return {
        "service": "HelixSupport",
        "env": {
            "SIGNING_KEY": SIGNING_KEY,
            "SIGNER_URL": SIGNER_URL,
            "INTERNAL_SERVICES": SERVICE_MAP,
            "SUPPORT_DIAGNOSTIC_FLAG": FLAG2,
        },
        "caller": {"user_id": claims.get("user_id"), "role": claims.get("role")},
    }


# ======================================================================================
# ADMIN TIER  (role == admin)
# ======================================================================================

@mcp.tool()
def troubleshoot(token: str, cmd: str = "status") -> dict:
    """Run a read-only platform troubleshooting command (admin only).

    Args:
        token: Your session token (admin role required).
        cmd: One of: status, sessions, services.
    """
    claims, err = _require_role(token, {"admin"})
    if err:
        return err
    if cmd == "services":
        data = {"services": SERVICE_MAP}
    elif cmd == "sessions":
        data = {"note": "session store is stateless (HMAC tokens); nothing to list"}
    else:
        data = {"platform": "HelixSupport", "health": "ok", "tenants": 1}
    return {"cmd": cmd, "result": data, "caller_role": claims.get("role")}


# ======================================================================================
# ADMIN TIER -- INTERNAL PROJECT BOARD  (role == admin)
# ======================================================================================
# This engineering board is only wired up for platform admins. `create_issue` carries the
# stage-4 command-injection sink; the other two are benign read tools that give the board a
# realistic surface. All three require an admin token -- which only stage 3 yields.

@mcp.tool()
def list_issues(token: str, state: str = "open") -> dict:
    """List issues on the internal engineering project board (admin only).

    Args:
        token: Your session token (admin role required).
        state: Filter by "open", "closed", or "all". Defaults to "open".
    """
    claims, err = _require_role(token, {"admin"})
    if err:
        return err
    return {"state": state, "issues": _current_board().list(state)}


@mcp.tool()
def get_issue(token: str, number: int) -> dict:
    """Get the full details of a single board issue by number (admin only).

    Args:
        token: Your session token (admin role required).
        number: Issue number to read.
    """
    claims, err = _require_role(token, {"admin"})
    if err:
        return err
    try:
        return _current_board().get(int(number))
    except BoardError as exc:
        return {"error": str(exc)}


@mcp.tool()
def create_issue(token: str, title: str, description: str = "", labels: str = "") -> dict:
    """Create a new issue on the internal engineering project board (admin only).

    Args:
        token: Your session token (admin role required).
        title: Short issue title.
        description: Longer issue body (optional).
        labels: Comma-separated labels, e.g. "bug,urgent" (optional).

    Returns:
        The created issue's summary plus the notification hook's output.
    """
    claims, err = _require_role(token, {"admin"})
    if err:
        return err

    # 1) Persist the issue SAFELY in local Python (records a mimic-commit). Not the bug.
    issue = _current_board().add_issue(title, description, labels)
    number = issue["number"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 2) Fire a local "automation / notification hook" that announces the new issue.
    #
    #    !!! VULNERABLE (CWE-78, CVE-2026-0756 class) !!!
    #    The untrusted `title` is concatenated straight into a shell command and run with
    #    shell=True. A title containing shell metacharacters (";", "|", "$()", backticks)
    #    breaks out and executes arbitrary OS commands. The command's combined stdout/stderr
    #    is returned as hook_output, so injected output is exfiltrated back to the caller.
    #    The container runs as root, so an injected `cat /root/flag.txt` yields FLAG 4.
    #
    #    THE FIX: never build shell strings from input -- log in Python, or use an argv list
    #    with shell=False (the analogue of the CVE's recommended execFile).
    hook = f'echo "[{ts}] new issue #{number}: {title}" >> {ACTIVITY_LOG}'
    proc = subprocess.run(hook, shell=True, capture_output=True, text=True, timeout=15)
    hook_output = (proc.stdout + proc.stderr).strip()

    return {
        "issue": number,
        "title": title,
        "column": issue["column"],
        "state": issue["state"],
        "labels": issue["labels"],
        "notified": True,
        "hook_output": hook_output,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
