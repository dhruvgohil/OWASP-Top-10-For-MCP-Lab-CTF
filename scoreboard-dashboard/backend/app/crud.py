"""All database access lives here — ORM only, no raw SQL.

Registration is serialised through a process-wide asyncio.Lock (the user's
explicit "single thread, no race condition" requirement) AND backed by the DB
UNIQUE constraints, so duplicate usernames/emails are impossible even under a
burst of simultaneous registrations.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from . import config, security
from .emailpolicy import normalise_email
from .models import Capture, Session, User
from .timeutil import utcnow

# Serialises the check-then-insert critical section of registration.
_registration_lock = asyncio.Lock()


class DuplicateUser(Exception):
    """Raised when username or email already exists."""


async def create_user(db: OrmSession, *, email: str, username: str, password: str) -> User:
    """Create a user atomically.

    The asyncio.Lock guarantees only one registration runs its check-then-insert
    at a time (no TOCTOU race); the UNIQUE constraint is the belt-and-braces
    backstop. Comparison is case-insensitive to stop near-duplicate takeovers
    (e.g. "Marcus" vs "marcus").

    The email domain policy is re-applied here rather than trusted from the
    caller: this is the only function that inserts a User row, so no present or
    future entry point can create an account outside the allowed domain.
    Re-normalising an already-normalised address is a no-op.
    """
    email_norm = normalise_email(email)  # raises InvalidEmail
    username_norm = username.strip()

    async with _registration_lock:
        # Case-insensitive existence check inside the lock.
        exists = db.execute(
            select(User.id).where(
                (func.lower(User.email) == email_norm)
                | (func.lower(User.username) == func.lower(username_norm))
            )
        ).first()
        if exists is not None:
            raise DuplicateUser()

        user = User(
            email=email_norm,
            username=username_norm,
            password_hash=security.hash_password(password),
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise DuplicateUser()
        db.refresh(user)
        return user


def get_user_by_identifier(db: OrmSession, identifier: str) -> User | None:
    """Look up a user by username or email (case-insensitive)."""
    ident = identifier.strip().lower()
    return db.execute(
        select(User).where(
            (func.lower(User.username) == ident) | (func.lower(User.email) == ident)
        )
    ).scalar_one_or_none()


# --- Sessions ----------------------------------------------------------------


def create_session(db: OrmSession, user: User) -> Session:
    sess = Session(
        token=security.new_session_token(),
        user_id=user.id,
        csrf_token=security.new_csrf_token(),
        expires_at=security.session_expiry(),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def get_valid_session(db: OrmSession, token: str) -> Session | None:
    sess = db.get(Session, token)
    if sess is None:
        return None
    if sess.expires_at <= utcnow():
        db.delete(sess)
        db.commit()
        return None
    return sess


def delete_session(db: OrmSession, token: str) -> None:
    sess = db.get(Session, token)
    if sess is not None:
        db.delete(sess)
        db.commit()


# --- Scoring -----------------------------------------------------------------


def user_score(db: OrmSession, user_id: int) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(Capture.points), 0)).where(Capture.user_id == user_id)
    ).scalar_one()
    return int(total)


def user_captured_stages(db: OrmSession, user_id: int) -> list[int]:
    rows = db.execute(
        select(Capture.flag_stage).where(Capture.user_id == user_id).order_by(Capture.flag_stage)
    ).scalars().all()
    return list(rows)


def record_capture(db: OrmSession, user_id: int, stage: int, points: int) -> bool:
    """Insert a capture. Returns False if already captured (idempotent)."""
    capture = Capture(user_id=user_id, flag_stage=stage, points=points)
    db.add(capture)
    try:
        db.commit()
    except IntegrityError:
        # UNIQUE(user_id, flag_stage) violated → already captured.
        db.rollback()
        return False
    return True


def scoreboard(db: OrmSession) -> list[dict]:
    """All players ranked high→low. Emails are never selected."""
    score_sum = func.coalesce(func.sum(Capture.points), 0)
    flags_count = func.count(Capture.id)
    rows = db.execute(
        select(
            User.username,
            score_sum.label("score"),
            flags_count.label("flags_captured"),
            func.max(Capture.captured_at).label("last_capture"),
        )
        .select_from(User)
        .outerjoin(Capture, Capture.user_id == User.id)
        .group_by(User.id)
        # Highest score first; ties broken by who reached it earliest.
        .order_by(score_sum.desc(), func.max(Capture.captured_at).asc().nulls_last(), User.username.asc())
    ).all()

    result = []
    for idx, r in enumerate(rows, start=1):
        result.append(
            {
                "rank": idx,
                "username": r.username,
                "score": int(r.score),
                "flags_captured": int(r.flags_captured),
            }
        )
    return result
