"""Calendar adapter factory — harness in-memory vs Google production.

CI / Virtual User always get ``StubCalendarAdapter`` (in-memory). Production
profiles return ``GoogleCalendarAdapter`` with soft-confirm write path unchanged.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Union

from capabilities.calendar.google import (
    GoogleCalendarAdapter,
    GoogleCalendarConfig,
    load_google_calendar_config,
)
from capabilities.calendar.store import CalendarStore
from harness.adapters import StubCalendarAdapter

CalendarAdapterImpl = Union[StubCalendarAdapter, GoogleCalendarAdapter]

DEFAULT_HARNESS_PROFILE = "config/calendar.harness.json"
DEFAULT_PRODUCTION_PROFILE = "config/calendar.production.example.json"


@dataclass(frozen=True)
class CalendarProfile:
    """Resolved calendar backend profile."""

    mode: str  # "memory" | "google"
    live: bool
    path: str
    google: GoogleCalendarConfig | None = None

    def to_public_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "mode": self.mode,
            "live": self.live,
            "path": self.path,
        }
        if self.google is not None:
            out["google"] = self.google.to_public_dict()
        return out


def load_calendar_profile(
    path: Path | str | None = None,
    *,
    env: Mapping[str, str] | None = None,
    root: Path | str | None = None,
) -> CalendarProfile:
    """Load calendar profile JSON. Defaults to harness in-memory."""
    environ = {k: str(v) for k, v in (os.environ if env is None else env).items()}
    base = Path(root) if root is not None else Path.cwd()

    explicit = path or environ.get("CALENDAR_PROFILE") or environ.get(
        "HARNESS_CALENDAR_PROFILE"
    )
    if explicit:
        profile_path = Path(explicit)
        if not profile_path.is_absolute():
            profile_path = base / profile_path
    else:
        # Production only when CALENDAR_MODE=google; else harness memory.
        mode_hint = (environ.get("CALENDAR_MODE") or "memory").strip().lower()
        if mode_hint == "google":
            profile_path = base / DEFAULT_PRODUCTION_PROFILE
        else:
            profile_path = base / DEFAULT_HARNESS_PROFILE

    data: dict[str, Any] = {}
    if profile_path.is_file():
        loaded = json.loads(profile_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded

    mode = str(data.get("mode") or environ.get("CALENDAR_MODE") or "memory").lower()
    if mode in {"harness", "stub", "in_memory", "in-memory"}:
        mode = "memory"
    if mode not in {"memory", "google"}:
        mode = "memory"

    google_cfg: GoogleCalendarConfig | None = None
    live = False
    if mode == "google":
        google_cfg = load_google_calendar_config(env=environ, config_path=profile_path)
        live = google_cfg.live

    return CalendarProfile(
        mode=mode,
        live=live,
        path=str(profile_path),
        google=google_cfg,
    )


def build_calendar_adapter(
    profile: CalendarProfile | None = None,
    *,
    store: CalendarStore | None = None,
    env: Mapping[str, str] | None = None,
    root: Path | str | None = None,
    config_path: Path | str | None = None,
) -> CalendarAdapterImpl:
    """Construct the calendar adapter for the active profile.

    Harness/CI: StubCalendarAdapter (in-memory).
    Production: GoogleCalendarAdapter (dry-run unless CALENDAR_LIVE=1).
    """
    resolved = profile or load_calendar_profile(config_path, env=env, root=root)
    if resolved.mode == "google":
        cfg = resolved.google or load_google_calendar_config(
            env=env, config_path=resolved.path
        )
        adapter = GoogleCalendarAdapter(config=cfg)
        if store is not None:
            adapter.attach_store(store)
        return adapter

    adapter = StubCalendarAdapter()
    if store is not None:
        adapter.attach_store(store)
    return adapter
