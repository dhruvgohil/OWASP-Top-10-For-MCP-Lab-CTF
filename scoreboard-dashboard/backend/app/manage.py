"""Operator CLI for the scoreboard database.

The SQLite file lives on the named Docker volume `scoreboard-data`, which is
deliberately NOT destroyed by `docker compose down` or by a rebuild — that is
why player accounts survive a restart. Wiping the whole volume (`down -v`) is
the blunt instrument; this module is the scalpel: it removes exactly the rows
you name and nothing else.

Nothing here is reachable over HTTP. It is an out-of-band admin path that
requires shell access to the container/host, so no web-facing authorisation
surface is added by its existence.

Usage (stack running):
    docker compose exec backend python -m app.manage list
    docker compose exec backend python -m app.manage delete <user> [...]
    docker compose exec backend python -m app.manage reset-password <user>

Usage (stack down — same volume, throwaway container):
    docker compose run --rm backend python -m app.manage list
"""
from __future__ import annotations

import argparse
import logging
import secrets
import sys

# passlib 1.7.4 probes bcrypt's version via a `__about__` attribute that bcrypt
# 4.x no longer exposes. It traps the failure and carries on hashing correctly,
# but the warning prints a traceback that would otherwise land right above a
# freshly generated password and read like the reset had failed.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

from sqlalchemy import func, or_, select  # noqa: E402

from . import security
from .config import ALLOWED_EMAIL_DOMAIN, DB_PATH, PASSWORD_MAX_LEN, PASSWORD_MIN_LEN
from .database import SessionLocal, init_db
from .emailpolicy import is_allowed
from .models import Capture, Session, User

# Ambiguity-free alphabet: no O/0, l/1/I. These get read aloud or copied off a
# screen, so a mistyped character is the failure mode worth designing out.
_PW_ALPHABET = "abcdefghijkmnpqrstuvwxyzACDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_password(groups: int = 3, size: int = 5) -> str:
    """A readable throwaway password, e.g. `Xk7tq-R2mVp-94hFd`."""
    return "-".join(
        "".join(secrets.choice(_PW_ALPHABET) for _ in range(size)) for _ in range(groups)
    )


def _resolve(db, identifier: str) -> User | None:
    """Find a user by numeric id, username, or email (case-insensitive).

    Username/email lookups are case-folded to match registration's own
    case-insensitive uniqueness rule, so `Marcus` and `marcus` resolve to the
    same account rather than silently missing.
    """
    ident = identifier.strip()
    if ident.isdigit():
        user = db.get(User, int(ident))
        if user is not None:
            return user

    return db.execute(
        select(User).where(
            or_(
                func.lower(User.username) == ident.lower(),
                func.lower(User.email) == ident.lower(),
            )
        )
    ).scalars().first()


def _score(db, user: User) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(Capture.points), 0)).where(Capture.user_id == user.id)
    ).scalar_one()
    return int(total)


def _describe(db, user: User) -> str:
    stages = db.execute(
        select(Capture.flag_stage).where(Capture.user_id == user.id).order_by(Capture.flag_stage)
    ).scalars().all()
    sessions = db.execute(
        select(func.count()).select_from(Session).where(Session.user_id == user.id)
    ).scalar_one()
    stage_txt = ",".join(str(s) for s in stages) if stages else "-"
    return (
        f"id={user.id:<4} {user.username:<20} {user.email:<30} "
        f"score={_score(db, user):<4} flags=[{stage_txt}] sessions={sessions} "
        f"joined={user.created_at:%Y-%m-%d %H:%M}"
    )


def cmd_list(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        users = db.execute(select(User).order_by(User.id)).scalars().all()
        if not users:
            print("No users in the database.")
            return 0
        for user in users:
            print(_describe(db, user))
        print(f"\n{len(users)} user(s) in {DB_PATH}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        targets: list[User] = []
        missing: list[str] = []
        for ident in args.identifiers:
            user = _resolve(db, ident)
            if user is None:
                missing.append(ident)
            elif user not in targets:
                targets.append(user)

        for ident in missing:
            print(f"not found: {ident}", file=sys.stderr)
        if not targets:
            return 1

        print("About to delete (captures and sessions go with them):")
        for user in targets:
            print("  " + _describe(db, user))

        if not args.yes:
            # Deletion is irreversible and the volume has no snapshot, so the
            # default path always stops for an explicit confirmation.
            try:
                answer = input("\nType 'yes' to confirm: ").strip().lower()
            except EOFError:
                answer = ""
            if answer != "yes":
                print("Aborted — nothing was deleted.")
                return 1

        for user in targets:
            # ORM delete honours cascade="all, delete-orphan" on User.captures
            # and User.sessions, and SQLite's FK cascade backs it up.
            db.delete(user)
        db.commit()
        print(f"Deleted {len(targets)} user(s).")
    return 0 if not missing else 1


def cmd_reset_captures(args: argparse.Namespace) -> int:
    """Drop a user's flag captures but keep the account and its credentials."""
    with SessionLocal() as db:
        user = _resolve(db, args.identifier)
        if user is None:
            print(f"not found: {args.identifier}", file=sys.stderr)
            return 1

        count = db.execute(
            select(func.count()).select_from(Capture).where(Capture.user_id == user.id)
        ).scalar_one()
        if count == 0:
            print(f"{user.username} has no captures.")
            return 0

        print(f"About to clear {count} capture(s) for {user.username} (score -> 0).")
        if not args.yes:
            try:
                answer = input("Type 'yes' to confirm: ").strip().lower()
            except EOFError:
                answer = ""
            if answer != "yes":
                print("Aborted — nothing was changed.")
                return 1

        for capture in list(user.captures):
            db.delete(capture)
        db.commit()
        print(f"Cleared {count} capture(s) for {user.username}.")
    return 0


def cmd_reset_password(args: argparse.Namespace) -> int:
    """Set a new password for a user, in person, without touching their score.

    This is the whole password-recovery story for the lab: addresses are fake by
    design (`test@gmail.com` receives nothing), so there is no mail-based
    reset to build and no self-service endpoint to attack. An operator with
    shell access is the only reset authority.
    """
    with SessionLocal() as db:
        user = _resolve(db, args.identifier)
        if user is None:
            print(f"not found: {args.identifier}", file=sys.stderr)
            return 1

        if args.password is not None:
            new_password = args.password
            if not PASSWORD_MIN_LEN <= len(new_password) <= PASSWORD_MAX_LEN:
                print(
                    f"password must be {PASSWORD_MIN_LEN}-{PASSWORD_MAX_LEN} characters",
                    file=sys.stderr,
                )
                return 1
        else:
            new_password = _generate_password()

        stages = db.execute(
            select(Capture.flag_stage).where(Capture.user_id == user.id).order_by(Capture.flag_stage)
        ).scalars().all()
        stage_txt = ",".join(str(s) for s in stages) if stages else "none"

        print(f"\nUser:     {user.username} <{user.email}>")
        print(f"Score:    {_score(db, user)}  (flags {stage_txt})")

        user.password_hash = security.hash_password(new_password)

        # Old sessions are revoked by default: whoever knew the previous password
        # (or was sitting on a live cookie) loses access the moment it is reset.
        revoked = 0
        if not args.keep_sessions:
            revoked = len(user.sessions)
            for session in list(user.sessions):
                db.delete(session)
        db.commit()

        if args.password is not None:
            print(f"Password set. {revoked} session(s) revoked.\n")
        else:
            print(f"\nNew password: {new_password}")
            print(f"(shown once; {revoked} session(s) revoked)\n")
    return 0


def cmd_check_emails(args: argparse.Namespace) -> int:
    """Report accounts whose email would not pass the current domain policy."""
    with SessionLocal() as db:
        users = db.execute(select(User).order_by(User.id)).scalars().all()
        offenders = [u for u in users if not is_allowed(u.email)]
        print(f"Policy: email domain must be exactly @{ALLOWED_EMAIL_DOMAIN}")
        if not offenders:
            print(f"All {len(users)} account(s) comply.")
            return 0
        print(f"\n{len(offenders)} of {len(users)} account(s) do NOT comply:")
        for user in offenders:
            print("  " + _describe(db, user))
        print("\nRemove them with:  delete " + " ".join(str(u.id) for u in offenders))
    # Non-zero so a script can act on it.
    return 1 if offenders else 0


def cmd_backup(args: argparse.Namespace) -> int:
    """Write a consistent single-file snapshot of the database.

    Do NOT back this database up by copying `scoreboard.db` on its own. The
    engine runs in WAL mode (see database.py), so recent commits live in
    `scoreboard.db-wal` until a checkpoint folds them into the main file — a
    plain file copy silently captures a stale, pre-commit state and looks
    perfectly valid when you open it.

    SQLite's online backup API reads through the WAL, so the output is exactly
    what a client would see right now, and it is safe to run while the app is
    serving traffic.
    """
    import sqlite3

    src = sqlite3.connect(DB_PATH)
    try:
        dest = sqlite3.connect(args.path)
        try:
            src.backup(dest)
            users = dest.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            dest.close()
    finally:
        src.close()

    print(f"Wrote {args.path} ({users} user(s)).")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Replace the live database with a snapshot, transactionally.

    Uses the same backup API in reverse rather than overwriting the file. A file
    swap would leave the old `-wal`/`-shm` behind, and SQLite would then replay
    that stale WAL over the restored contents — corrupting exactly the data you
    were trying to bring back.
    """
    import os
    import sqlite3

    if not os.path.exists(args.path):
        print(f"no such file: {args.path}", file=sys.stderr)
        return 1

    src = sqlite3.connect(args.path)
    try:
        incoming = src.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        with SessionLocal() as db:
            current = db.execute(select(func.count()).select_from(User)).scalar_one()

        print(f"Replace the live database ({current} user(s)) with {args.path} ({incoming} user(s))?")
        if not args.yes:
            try:
                answer = input("Type 'yes' to confirm: ").strip().lower()
            except EOFError:
                answer = ""
            if answer != "yes":
                print("Aborted — nothing was changed.")
                return 1

        dest = sqlite3.connect(DB_PATH)
        try:
            src.backup(dest)
        finally:
            dest.close()
    finally:
        src.close()

    print(f"Restored {incoming} user(s) from {args.path}.")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    """Invalidate a user's server-side sessions without touching their data."""
    with SessionLocal() as db:
        user = _resolve(db, args.identifier)
        if user is None:
            print(f"not found: {args.identifier}", file=sys.stderr)
            return 1
        count = len(user.sessions)
        for session in list(user.sessions):
            db.delete(session)
        db.commit()
        print(f"Revoked {count} session(s) for {user.username}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.manage",
        description="Admin operations on the scoreboard database.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list every user with score and captured stages")
    p_list.set_defaults(func=cmd_list)

    p_del = sub.add_parser("delete", help="delete users by id, username, or email")
    p_del.add_argument("identifiers", nargs="+", metavar="USER")
    p_del.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    p_del.set_defaults(func=cmd_delete)

    p_reset = sub.add_parser("reset-captures", help="clear a user's flags, keep the account")
    p_reset.add_argument("identifier", metavar="USER")
    p_reset.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    p_reset.set_defaults(func=cmd_reset_captures)

    p_pw = sub.add_parser("reset-password", help="set a new password for a user")
    p_pw.add_argument("identifier", metavar="USER")
    p_pw.add_argument(
        "-p",
        "--password",
        help="use this password instead of a generated one",
    )
    p_pw.add_argument(
        "--keep-sessions",
        action="store_true",
        help="do not revoke the user's existing logins",
    )
    p_pw.set_defaults(func=cmd_reset_password)

    p_check = sub.add_parser(
        "check-emails", help=f"list accounts outside @{ALLOWED_EMAIL_DOMAIN}"
    )
    p_check.set_defaults(func=cmd_check_emails)

    p_backup = sub.add_parser(
        "backup", help="write a consistent snapshot (WAL-safe; do not cp the .db)"
    )
    p_backup.add_argument("path", metavar="FILE")
    p_backup.set_defaults(func=cmd_backup)

    p_restore = sub.add_parser("restore", help="replace the live DB with a snapshot")
    p_restore.add_argument("path", metavar="FILE")
    p_restore.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    p_restore.set_defaults(func=cmd_restore)

    p_logout = sub.add_parser("logout", help="revoke a user's active sessions")
    p_logout.add_argument("identifier", metavar="USER")
    p_logout.set_defaults(func=cmd_logout)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Creates the schema if the volume is brand new; a no-op otherwise, so the
    # CLI works against a stack that has never been started.
    init_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
