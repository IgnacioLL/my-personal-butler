"""Calendar capability — in-memory store + soft-confirm writes.

Import service from capabilities.calendar.service directly when needed alongside
harness clocks to avoid circular package init.

Factory/google are imported lazily via capabilities.calendar.factory /
capabilities.calendar.google to avoid circular import with harness.adapters.
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
