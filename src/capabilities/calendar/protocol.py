"""Shared calendar adapter protocol — harness stub and Google production."""

from __future__ import annotations

from typing import Any, Protocol

from capabilities.calendar.store import CalendarStore


class CalendarAdapter(Protocol):
    """Side-effect adapter for calendar writes.

    INV-APPR-003: create/modify/cancel must only run after soft-confirm Accept
    via ActionGateway.execute — never on propose.
    """

    create_count: int
    modify_count: int
    cancel_count: int
    store: CalendarStore

    def attach_store(self, store: CalendarStore) -> None:
        """Share CalendarStore so service conflict checks see writes."""

    def create(self, event: dict[str, Any]) -> dict[str, Any]:
        """Create an event. Called only after soft-confirm Accept."""

    def modify(self, event_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Modify an event. Soft confirm required."""

    def cancel(self, event_id: str) -> bool:
        """Cancel/delete an event. Soft confirm required."""

    def reset(self) -> None:
        """Clear counters + store (tests)."""

    @property
    def events(self) -> list[dict[str, Any]]:
        """Mirror of known events (local store)."""
