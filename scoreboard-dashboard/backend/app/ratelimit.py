"""Tiny in-memory sliding-window rate limiter.

Sufficient for a single-process lab dashboard: keeps brute-force login and
flag-spam in check without an external store. Keyed by an arbitrary string
(e.g. "login:<ip>:<identifier>" or "submit:<user_id>").
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def check(key: str, max_attempts: int, window_seconds: int) -> bool:
    """Record an attempt. Return True if allowed, False if over the limit."""
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        dq = _hits[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_attempts:
            return False
        dq.append(now)
        return True
