"""Quiet hours policy for proactive emissions and outbound calls."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo


def normalize_quiet_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Merge profile quiet_hours shapes into a single checkable config."""
    if not raw:
        return {"enabled": False}
    enabled = bool(raw.get("enabled", True))
    start = str(raw.get("start") or raw.get("no_calls_after") or "22:00")
    end = str(raw.get("end") or "07:30")
    return {
        "enabled": enabled,
        "start": start,
        "end": end,
        "no_calls_after": raw.get("no_calls_after") or start,
    }


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=hour, minute=minute)


def is_in_quiet_hours(
    now: datetime,
    quiet: dict[str, Any] | None,
    *,
    timezone: str = "Europe/Madrid",
) -> bool:
    """True when local time falls inside the configured quiet window."""
    cfg = normalize_quiet_config(quiet)
    if not cfg.get("enabled"):
        return False

    tz = ZoneInfo(timezone)
    local = now.astimezone(tz)
    start = _parse_hhmm(str(cfg["start"]))
    end = _parse_hhmm(str(cfg["end"]))
    current = local.time()

    if start <= end:
        return start <= current < end
    # Overnight span (e.g. 22:00 → 07:30).
    return current >= start or current < end


def blocks_proactive(
    now: datetime,
    quiet: dict[str, Any] | None,
    *,
    timezone: str = "Europe/Madrid",
) -> tuple[bool, str]:
    if is_in_quiet_hours(now, quiet, timezone=timezone):
        return True, "quiet_hours"
    return False, ""


def blocks_call(
    now: datetime,
    quiet: dict[str, Any] | None,
    *,
    timezone: str = "Europe/Madrid",
    emergency: bool = False,
) -> tuple[bool, str]:
    if emergency:
        return False, ""
    return blocks_proactive(now, quiet, timezone=timezone)


__all__ = [
    "blocks_call",
    "blocks_proactive",
    "is_in_quiet_hours",
    "normalize_quiet_config",
]
