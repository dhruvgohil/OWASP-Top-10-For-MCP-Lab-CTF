"""SQLAlchemy engine + session factory (SQLite).

All persistence goes through the ORM, so every query is parameterised — there
is no string-built SQL anywhere in the app, which removes the SQL-injection
surface entirely.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DB_PATH

# Make sure the parent directory of the SQLite file exists (it's a mounted
# volume in Docker but this keeps a bare `uvicorn` run working too).
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    # FastAPI may touch a session from a threadpool worker; SQLite needs this.
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """Enforce FK constraints and use WAL for better concurrent reads."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so they register on the metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
