"""Time helpers.

SQLite does not persist timezone info, so a `DateTime(timezone=True)` column
round-trips as a *naive* datetime. To avoid offset-naive vs offset-aware
comparison errors we standardise on **naive UTC** everywhere internally.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current time as a naive UTC datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
