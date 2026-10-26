"""Central configuration for the HELIXCHAIN scoreboard dashboard.

Everything security-relevant that a client must never influence lives here:
the flag -> points table, the session secret, and cookie policy. The client
never sees this module and cannot supply points, stages, or user ids.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


def _env(key: str, default: str) -> str:
    val = os.getenv(key)
    return val if val is not None and val != "" else default


@dataclass(frozen=True)
class FlagDef:
    stage: int
    name: str
    value: str
    points: int


# The authoritative flag catalogue. Values default to the combined-chain-lab's
# built-in flags (see combined-chain-lab/docker-compose.yml) but can be
# overridden with FLAG1..FLAG4 so the dashboard matches a customised lab.
# Points are assigned by stage difficulty / number of steps (multiples of 10).
FLAGS: tuple[FlagDef, ...] = (
    FlagDef(1, "Information disclosure", _env("FLAG1", "FLAG{CHAIN_STATUS_INFO_DISCLOSURE}"), 10),
    FlagDef(2, "Signer privilege escalation", _env("FLAG2", "FLAG{CHAIN_SIGNER_PRIVILEGE_ESCALATION}"), 20),
    FlagDef(3, "Admin BOLA / confused deputy", _env("FLAG3", "FLAG{CHAIN_ADMIN_BOLA_CONFUSED_DEPUTY}"), 30),
    FlagDef(4, "Remote code execution", _env("FLAG4", "FLAG{CHAIN_ADMIN_RCE_COMMAND_INJECTION}"), 40),
)

TOTAL_POINTS = sum(f.points for f in FLAGS)

# The lab this dashboard tracks. Only the link is exposed to clients.
LAB_URL = _env("LAB_URL", "http://localhost:3100")
LAB_NAME = "HELIXCHAIN"

# --- Session / cookie policy -------------------------------------------------
# A stable secret keeps signed cookies valid across restarts. If unset we
# generate an ephemeral one (fine for a single-process dev run; set it in prod
# so existing sessions survive a restart).
SESSION_SECRET = _env("SESSION_SECRET", secrets.token_urlsafe(48))
SESSION_COOKIE_NAME = "helix_sb_session"
SESSION_TTL_SECONDS = int(_env("SESSION_TTL_SECONDS", str(60 * 60 * 12)))  # 12h
# COOKIE_SECURE=1 in HTTPS deployments. Default 0 so the cookie works over
# http://localhost during local lab use.
COOKIE_SECURE = _env("COOKIE_SECURE", "0") == "1"
COOKIE_SAMESITE = "lax"

# --- Validation policy -------------------------------------------------------
USERNAME_PATTERN = r"^[A-Za-z0-9_-]{3,20}$"
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128
EMAIL_MAX_LEN = 254  # RFC 5321 practical maximum, matches the users.email column

# Only addresses in this exact domain may register. Operator-controlled via env
# (never client-controlled); see app/emailpolicy.py for how it is enforced.
# Lower-cased here so the comparison site never has to think about case.
ALLOWED_EMAIL_DOMAIN = _env("ALLOWED_EMAIL_DOMAIN", "gmail.com").strip().lower().lstrip("@")

# --- Database ----------------------------------------------------------------
DB_PATH = _env("DB_PATH", "/data/scoreboard.db")

# --- Rate limiting -----------------------------------------------------------
LOGIN_MAX_ATTEMPTS = 10          # per window, per (ip, identifier)
LOGIN_WINDOW_SECONDS = 300       # 5 minutes
SUBMIT_MAX_ATTEMPTS = 30         # per window, per user
SUBMIT_WINDOW_SECONDS = 60
