"""Calendar capability — in-memory store, conflict-aware suggestions, soft-confirm writes.

Import service from capabilities.calendar.service directly when needed alongside
harness clocks to avoid circular package init.
"""

from capabilities.calendar.parse import ParsedCalendarEvent, looks_like_schedule, parse_schedule
from capabilities.calendar.store import CalendarEvent, CalendarStore, Conflict, FreeSlot

__all__ = [
    "CalendarEvent",
    "CalendarStore",
    "Conflict",
    "FreeSlot",
    "ParsedCalendarEvent",
    "looks_like_schedule",
    "parse_schedule",
]
