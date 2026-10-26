"""The single source of truth for which email addresses may hold an account.

Policy: the address must be syntactically valid AND its domain must be exactly
`ALLOWED_EMAIL_DOMAIN` (default `gmail.com`). Deliverability is NOT checked
— `test@gmail.com` is a perfectly acceptable lab identity; we care about
the domain, not whether a mailbox exists.

Why a dedicated module rather than a regex on the request schema:

* A naive `email.endswith("@gmail.com")` is bypassable. `email_validator`
  parses the address properly, so the checks below see the *normalised* domain:
    - `a@gmail.com.evil.com`   -> domain is `gmail.com.evil.com`  (reject)
    - `a@mail.gmail.com`       -> domain is `mail.gmail.com`      (reject)
    - `a@net-squаre.com` (Cyrillic а) -> IDNA-normalised to `xn--net-squre-6yh.com` (reject)
    - `"x@evil.com"@gmail.com` -> quoted local parts rejected outright
    - `Foo <a@gmail.com>`      -> display names rejected outright
  The comparison is exact equality against the normalised ASCII domain, never a
  suffix test, so there is no "looks like it ends with the domain" trick.

* Every write path funnels through `normalise_email()`: the HTTP schema, the
  CRUD layer, and the admin CLI. Adding a new entry point without the check
  would require deliberately bypassing the only function that builds a stored
  email value.
"""
from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

from .config import ALLOWED_EMAIL_DOMAIN, EMAIL_MAX_LEN


class InvalidEmail(ValueError):
    """Raised when an address is malformed or outside the allowed domain."""


# Shown to the client verbatim. It leaks nothing (the domain requirement is
# public by design) and tells the player exactly what to fix.
POLICY_MESSAGE = f"Enter a valid email address ending in @{ALLOWED_EMAIL_DOMAIN}"


def normalise_email(raw: str) -> str:
    """Validate `raw` against the policy and return the canonical stored form.

    The returned value is lower-cased end-to-end so it matches the
    case-insensitive uniqueness rule used at registration and login — nobody
    gets a second account by capitalising their local part.
    """
    if not isinstance(raw, str):
        raise InvalidEmail(POLICY_MESSAGE)

    candidate = raw.strip()
    if not candidate or len(candidate) > EMAIL_MAX_LEN:
        raise InvalidEmail(POLICY_MESSAGE)

    try:
        result = validate_email(
            candidate,
            # These addresses are deliberately fake, so never touch DNS: it
            # would be slow, would fail offline, and is not what we're gating on.
            check_deliverability=False,
            # ASCII only. Non-ASCII local parts would need SMTPUTF8 and open an
            # avenue for visually-confusable identities on the scoreboard.
            allow_smtputf8=False,
            allow_quoted_local=False,
            allow_domain_literal=False,
            allow_display_name=False,
        )
    except EmailNotValidError as exc:
        raise InvalidEmail(POLICY_MESSAGE) from exc

    # `ascii_domain` is the IDNA-normalised (punycode) domain, so homograph
    # lookalikes never compare equal to the real thing. Exact match, not suffix.
    if result.ascii_domain.lower() != ALLOWED_EMAIL_DOMAIN:
        raise InvalidEmail(POLICY_MESSAGE)

    return result.normalized.lower()


def is_allowed(raw: str) -> bool:
    """Non-raising form, for reporting tools."""
    try:
        normalise_email(raw)
    except InvalidEmail:
        return False
    return True
