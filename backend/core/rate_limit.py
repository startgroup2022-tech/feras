"""Lightweight in-process rate limiting.

A sliding-window counter keyed by client identity. This is deliberately simple
and dependency-free: it protects the login endpoint from trivial brute force
inside a single process. When the platform scales horizontally this should be
swapped for a shared store (Redis) behind the same ``RateLimiter`` interface.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: int) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Record an event and return True if the key is still within limits."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_events:
                return False
            bucket.append(now)
            return True

    def retry_after(self, key: str) -> int:
        with self._lock:
            bucket = self._events.get(key)
            if not bucket:
                return 0
            remaining = self.window_seconds - (time.monotonic() - bucket[0])
            return max(1, int(remaining))

    def reset(self, key: str | None = None) -> None:
        """Clear counters. Used by tests and after a successful login."""
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)
