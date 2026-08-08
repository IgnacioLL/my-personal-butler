"""Fake clock for harness and CI — never sleep wall-clock for cron/expiry.

API intent (agent-plan/testing/harnesses-and-fixtures.md):
  - clock.now()
  - clock.advance(duration)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Union

Duration = Union[timedelta, float, int]


def _as_timedelta(duration: Duration) -> timedelta:
    if isinstance(duration, timedelta):
        return duration
    if isinstance(duration, (int, float)):
        return timedelta(seconds=float(duration))
    raise TypeError(f"duration must be timedelta|seconds, got {type(duration)!r}")


class FakeClock:
    """Deterministic clock for reminders, approval expiry, and heartbeats."""

    def __init__(self, start: datetime | None = None) -> None:
        if start is None:
            start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        elif start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, duration: Duration) -> datetime:
        """Advance the clock by duration (timedelta or seconds) and return new now()."""
        self._now = self._now + _as_timedelta(duration)
        return self._now

    def set(self, when: datetime) -> datetime:
        """Jump to an absolute time (harness-only; prefer advance for scenario steps)."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        self._now = when
        return self._now
