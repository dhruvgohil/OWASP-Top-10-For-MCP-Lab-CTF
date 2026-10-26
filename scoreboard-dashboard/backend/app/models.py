"""ORM models.

Note the deliberate absence of any mutable "score" column on User. A user's
score is always DERIVED as SUM(captures.points) at read time, so there is no
field a client could ever tamper with to inflate their standing.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .timeutil import utcnow


def _utcnow() -> datetime:
    # Naive UTC — SQLite does not persist tzinfo, so we keep everything naive
    # UTC end-to-end to avoid offset-naive/aware comparison errors.
    return utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # UNIQUE constraints are the atomic guarantee against duplicate accounts —
    # even if two registrations race, the second INSERT fails at the DB level.
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    captures: Mapped[list["Capture"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    # Opaque 256-bit token — the primary key IS the secret handed to the client
    # (inside a signed httpOnly cookie). Server-side storage means logout and
    # expiry can invalidate it immediately.
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class Capture(Base):
    __tablename__ = "captures"
    # One credit per (user, flag stage): resubmitting a flag can never award
    # points twice.
    __table_args__ = (UniqueConstraint("user_id", "flag_stage", name="uq_user_stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    flag_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    # Points are copied from the server-side flag table at capture time; the
    # client never supplies this value.
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="captures")
