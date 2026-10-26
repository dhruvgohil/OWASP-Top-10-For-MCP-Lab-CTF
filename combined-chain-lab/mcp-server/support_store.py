"""Local, pure-Python data store for the "HelixSupport" help-desk MCP server.

Mirrors the persistence style of the sibling command-injection lab's `board_store.py`:
plain JSON files on disk, no external database, no network. Everything the lab needs
(customer accounts, support tickets, ticket notes) lives here so the whole environment
is fully offline and Docker-local.

SAFETY / SCOPE NOTE: this module is deliberately a *faithful* little data layer. The
vulnerabilities this lab teaches are NOT in here -- they live in how `support_mcp.py`
authorizes (or fails to authorize) access to these records. In particular this store
exposes both an ownership-checked read (`get_ticket`) and an *unchecked* append
(`add_note`); the MCP tool layer is what turns that asymmetry into the BOLA objective.
"""

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StoreError(Exception):
    """Benign, expected errors (missing user/ticket, duplicate username, ...)."""


# First seeded ticket number. Attacker-created tickets count up from here, so the
# victim's ticket keeps its memorable, otto-style id (4201).
FIRST_TICKET = 4201


class SupportStore:
    """A tiny help-desk backing store: customers + tickets + notes."""

    def __init__(self, root: str, victim_recovery_code: str):
        self.root = Path(root)
        self.users_path = self.root / "users.json"
        self.tickets_path = self.root / "tickets.json"
        self.meta_path = self.root / "meta.json"
        self._victim_recovery_code = victim_recovery_code
        self._ensure()

    # ----------------------------------------------------------------- bootstrap
    def _ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.users_path.exists():
            self._write(self.users_path, {})
        if not self.tickets_path.exists():
            self._write(self.tickets_path, {})
        if not self.meta_path.exists():
            self._write(self.meta_path, {"next_ticket": FIRST_TICKET})
        if self._is_empty():
            self._seed()

    def _is_empty(self) -> bool:
        return not self._read(self.users_path)

    def _seed(self) -> None:
        """Populate a realistic starter tenant on first boot."""
        # An ordinary customer. Its ticket #4201 is a realistic DECOY: resetting john only
        # yields a throwaway recovery code, not a flag. The crown jewel now lives on the
        # ADMIN account (below) -- reaching it is the stage-3 objective.
        self._put_user(
            {
                "user_id": "usr_john",
                "username": "john",
                "password": "Rainy-Otter-4417",
                "email": "john@northwind.example",
                "role": "user",
                "plan": "Business",
                "company": "Northwind Trading",
                "recovery_code": "RC-" + secrets.token_hex(4).upper(),
            }
        )
        # A second ordinary customer, so `search_customers` returns realistic breadth.
        self._put_user(
            {
                "user_id": "usr_alice",
                "username": "alice",
                "password": "Copper-Lantern-8820",
                "email": "alice@brightpath.example",
                "role": "user",
                "plan": "Starter",
                "company": "Brightpath Design",
                "recovery_code": "RC-" + secrets.token_hex(4).upper(),
            }
        )
        # A back-office support agent account (its credentials are NOT given to the
        # attacker; reaching the support tier is meant to happen via the signer flaw).
        self._put_user(
            {
                "user_id": "usr_support",
                "username": "support_agent",
                "password": secrets.token_urlsafe(12),
                "email": "agent@helixsupport.example",
                "role": "support",
                "plan": "-",
                "company": "HelixSupport",
                "recovery_code": "RC-" + secrets.token_hex(4).upper(),
            }
        )
        # The platform ADMIN account. Its credentials are NOT handed out, and its
        # `recovery_code` is the crown jewel (FLAG 3): a confused-deputy support agent that
        # "resets" this account surfaces the recovery code AND a fresh admin password in its
        # response -- which is exactly what unlocks the admin tier (and stage 4).
        self._put_user(
            {
                "user_id": "usr_admin",
                "username": "admin",
                "password": secrets.token_urlsafe(12),
                "email": "root@helixsupport.example",
                "role": "admin",
                "plan": "-",
                "company": "HelixSupport",
                "recovery_code": self._victim_recovery_code,
            }
        )

        # Victim ticket #4201, plus a decoy so listings look real.
        self._put_ticket(
            {
                "ticket_id": 4201,
                "owner_id": "usr_john",
                "owner_username": "john",
                "subject": "Payments intermittently failing at checkout",
                "body": (
                    "About once in every ten checkouts the payment step times out and the "
                    "customer has to retry. Started roughly a week ago. Please investigate."
                ),
                "status": "open",
                "notes": [
                    {
                        "author": "john",
                        "body": "Happens on both card and wallet payments.",
                        "at": _now(),
                    }
                ],
                "created_at": _now(),
            }
        )
        self._put_ticket(
            {
                "ticket_id": 4202,
                "owner_id": "usr_alice",
                "owner_username": "alice",
                "subject": "Cannot update billing address",
                "body": "The billing address form throws a validation error on save.",
                "status": "open",
                "notes": [],
                "created_at": _now(),
            }
        )
        # The ADMIN's own ticket. Its number is RANDOMIZED per seed (i.e. per tenant/player)
        # so it can't be memorized or copy-pasted from the walkthrough -- players must find it
        # the intended way: at support tier list_tickets returns the whole queue, and this row
        # is unmistakable (owner_username "admin" + the recertification subject below). Chosen
        # from [4210, 4290] so it never collides with the decoys (4201/4202) or player-created
        # tickets (which start at next_ticket=4300). It is the stage-3 target: BOLA-write a
        # poisoned note into it, then have a support agent "resolve" it ->
        # reset_password(usr_admin) -> FLAG 3.
        admin_ticket = 4210 + secrets.randbelow(81)
        self._put_ticket(
            {
                "ticket_id": admin_ticket,
                "owner_id": "usr_admin",
                "owner_username": "admin",
                "subject": "Privileged access recertification — rotate admin credentials",
                "body": (
                    "Routine quarterly recertification for the platform admin account. Per "
                    "policy the admin credential must be rotated and the account recovery "
                    "details re-confirmed by whichever support engineer picks this up."
                ),
                "status": "open",
                "notes": [
                    {
                        "author": "admin",
                        "body": "Opened by automated compliance. Please action before quarter end.",
                        "at": _now(),
                    }
                ],
                "created_at": _now(),
            }
        )
        self._set_meta("next_ticket", 4300)

    # --------------------------------------------------------------- low-level IO
    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _set_meta(self, key: str, value) -> None:
        meta = self._read(self.meta_path)
        meta[key] = value
        self._write(self.meta_path, meta)

    def _put_user(self, user: dict) -> None:
        users = self._read(self.users_path)
        users[user["user_id"]] = user
        self._write(self.users_path, users)

    def _put_ticket(self, ticket: dict) -> None:
        tickets = self._read(self.tickets_path)
        tickets[str(ticket["ticket_id"])] = ticket
        self._write(self.tickets_path, tickets)

    # -------------------------------------------------------------------- users
    def _user_by_name(self, username: str) -> dict | None:
        for user in self._read(self.users_path).values():
            if user["username"].lower() == username.lower():
                return user
        return None

    def _user_by_id(self, user_id: str) -> dict | None:
        return self._read(self.users_path).get(user_id)

    def create_user(self, username: str, email: str = "") -> dict:
        username = (username or "").strip()
        if not username:
            raise StoreError("A username is required.")
        if self._user_by_name(username):
            raise StoreError(f"Username '{username}' is already taken.")
        user = {
            "user_id": "usr_" + secrets.token_hex(4),
            "username": username,
            # Auto-generated credential returned to the caller (like a real signup).
            "password": secrets.token_urlsafe(9),
            "email": email or f"{username}@customer.example",
            "role": "user",
            "plan": "Starter",
            "company": "(self-service signup)",
            "recovery_code": "RC-" + secrets.token_hex(4).upper(),
        }
        self._put_user(user)
        return user

    def check_password(self, username: str, password: str) -> dict | None:
        user = self._user_by_name(username)
        if user and secrets.compare_digest(str(user["password"]), str(password or "")):
            return user
        return None

    def get_user(self, user_id: str) -> dict | None:
        return self._user_by_id(user_id)

    def search_users(self, query: str) -> list[dict]:
        query = (query or "").strip().lower()
        out = []
        for user in self._read(self.users_path).values():
            haystack = " ".join(
                str(user.get(k, "")) for k in ("username", "email", "company", "user_id")
            ).lower()
            if not query or query in haystack:
                out.append(self._public_user(user))
        return sorted(out, key=lambda u: u["username"])

    def update_user(self, user_id: str, fields: dict) -> dict:
        user = self._user_by_id(user_id)
        if not user:
            raise StoreError(f"No customer with id '{user_id}'.")
        for key in ("email", "plan", "company"):
            if key in fields and fields[key] is not None:
                user[key] = fields[key]
        self._put_user(user)
        return self._public_user(user)

    def reset_password(self, user_id: str, new_password: str = "") -> dict:
        user = self._user_by_id(user_id)
        if not user:
            raise StoreError(f"No customer with id '{user_id}'.")
        user["password"] = new_password or secrets.token_urlsafe(9)
        self._put_user(user)
        # A real "account recovery" flow surfaces a recovery code; that is the leak.
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "new_password": user["password"],
            "recovery_code": user["recovery_code"],
        }

    @staticmethod
    def _public_user(user: dict) -> dict:
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"],
            "plan": user["plan"],
            "company": user["company"],
            "role": user["role"],
        }

    # ------------------------------------------------------------------ tickets
    def create_ticket(self, owner: dict, subject: str, body: str = "") -> dict:
        meta = self._read(self.meta_path)
        number = int(meta.get("next_ticket", FIRST_TICKET))
        ticket = {
            "ticket_id": number,
            "owner_id": owner["user_id"],
            "owner_username": owner["username"],
            "subject": subject or "(no subject)",
            "body": body or "",
            "status": "open",
            "notes": [],
            "created_at": _now(),
        }
        self._put_ticket(ticket)
        self._set_meta("next_ticket", number + 1)
        return ticket

    def get_ticket(self, ticket_id: int) -> dict:
        ticket = self._read(self.tickets_path).get(str(ticket_id))
        if not ticket:
            raise StoreError(f"Ticket #{ticket_id} does not exist.")
        return ticket

    def list_tickets_for(self, owner_id: str) -> list[dict]:
        out = []
        for ticket in self._read(self.tickets_path).values():
            if ticket["owner_id"] == owner_id:
                out.append(self._ticket_summary(ticket))
        return sorted(out, key=lambda t: t["ticket_id"])

    def list_all_tickets(self) -> list[dict]:
        tickets = self._read(self.tickets_path).values()
        return sorted((self._ticket_summary(t) for t in tickets), key=lambda t: t["ticket_id"])

    def add_note(self, ticket_id: int, author: str, body: str) -> dict:
        ticket = self.get_ticket(ticket_id)
        ticket["notes"].append({"author": author, "body": body, "at": _now()})
        self._put_ticket(ticket)
        return ticket

    @staticmethod
    def _ticket_summary(ticket: dict) -> dict:
        return {
            "ticket_id": ticket["ticket_id"],
            "owner_username": ticket["owner_username"],
            "subject": ticket["subject"],
            "status": ticket["status"],
            "notes": len(ticket["notes"]),
        }
