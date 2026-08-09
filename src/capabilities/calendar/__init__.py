"""Calendar capability — in-memory store, Google production adapter, soft-confirm writes.

Import service from capabilities.calendar.service directly when needed alongside
harness clocks to avoid circular package init.
"""

from capabilities.calendar.factory import (
    CalendarProfile,
    build_calendar_adapter,
    load_calendar_profile,
)
from capabilities.calendar.google import (
    GoogleCalendarAdapter,
    GoogleCalendarConfig,
    GoogleCalendarError,
    load_google_calendar_config,
)
from capabilities.calendar.parse import ParsedCalendarEvent, looks_like_schedule, parse_schedule
from capabilities.calendar.store import CalendarEvent, CalendarStore, Conflict, FreeSlot

__all__ = [
    "CalendarEvent",
    "CalendarProfile",
    "CalendarStore",
    "Conflict",
    "FreeSlot",
    "GoogleCalendarAdapter",
    "GoogleCalendarConfig",
    "GoogleCalendarError",
    "ParsedCalendarEvent",
    "build_calendar_adapter",
    "load_calendar_profile",
    "load_google_calendar_config",
    "looks_like_schedule",
    "parse_schedule",
]
