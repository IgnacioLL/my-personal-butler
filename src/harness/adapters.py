"""Stub adapters for gated side effects (calendar, buy, book, self-mod, cron).

No live services — counters for INV assertions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from capabilities.calendar.store import CalendarStore


class _PauseAware(Protocol):
    @property
    def is_paused(self) -> bool: ...


@dataclass
class StubCalendarAdapter:
    """In-memory calendar — create/modify must only be called after soft confirm.

    INV-APPR-003: create_count stays 0 until Accept executes.
    """

    store: CalendarStore = field(default_factory=CalendarStore)
    create_count: int = 0
    modify_count: int = 0
    cancel_count: int = 0

    def attach_store(self, store: CalendarStore) -> None:
        """Share an external CalendarStore (service + adapter see same events)."""
        # Preserve any events already written via this adapter.
        if self.store is store:
            return
        if self.store.events and not store.events:
            for evt in self.store.list_all():
                store.events[evt.id] = evt
        elif self.store.events and store.events:
            for evt in self.store.list_all():
                if evt.id not in store.events:
                    store.events[evt.id] = evt
        self.store = store

    @property
    def events(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.store.list_all()]

    def create(self, event: dict[str, Any]) -> dict[str, Any]:
        self.create_count += 1
        payload = dict(event)
        payload.setdefault("id", f"evt-{self.create_count}")
        stored = self.store.upsert_from_payload(payload)
        return stored.to_dict()

    def modify(self, event_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.modify_count += 1
        updated = self.store.modify(event_id, patch)
        return updated.to_dict()

    def cancel(self, event_id: str) -> bool:
        self.cancel_count += 1
        return self.store.cancel(event_id)

    def reset(self) -> None:
        self.store.clear()
        self.create_count = 0
        self.modify_count = 0
        self.cancel_count = 0


class BookingAdapterError(RuntimeError):
    """Raised when stub booking execute fails (slot gone / portal error)."""


@dataclass
class StubCommerceAdapter:
    """Buy / book execute counters — must stay 0 until Accept.

    Buy is always dry-run in harness (no live card charge). INV-PAY-*:
    freeze/caps gate execute before this adapter is reached.
    """

    buy_count: int = 0
    buy_attempt_count: int = 0
    book_count: int = 0
    book_attempt_count: int = 0
    buys: list[dict[str, Any]] = field(default_factory=list)
    books: list[dict[str, Any]] = field(default_factory=list)
    book_failures: list[dict[str, Any]] = field(default_factory=list)
    fail_next_book: bool = False
    fail_book_message: str = "slot_unavailable"
    dry_run: bool = True

    def buy(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Dry-run purchase. INV-PAY / hard-approve: only after Accept under caps."""
        self.buy_attempt_count += 1
        self.buy_count += 1
        receipt = {
            "receipt_id": f"buy-{self.buy_count}",
            "dry_run": True if payload.get("dry_run", self.dry_run) else False,
            "mode": "dry_run",
            **payload,
        }
        receipt["dry_run"] = True
        receipt["mode"] = "dry_run"
        self.buys.append(receipt)
        return receipt

    def book(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute reservation. INV-BOOK-001: only called after Accept.

        INV-BOOK-002: on failure raises — caller must not mark user-facing success.
        """
        self.book_attempt_count += 1
        force_fail = bool(payload.get("force_fail")) or self.fail_next_book
        if force_fail:
            self.fail_next_book = False
            message = str(
                payload.get("fail_reason") or self.fail_book_message or "booking_failed"
            )
            self.book_failures.append({"reason": message, "payload": dict(payload)})
            raise BookingAdapterError(message)
        self.book_count += 1
        confirmation = {"booking_id": f"book-{self.book_count}", **payload}
        self.books.append(confirmation)
        return confirmation

    def reset(self) -> None:
        self.buy_count = 0
        self.buy_attempt_count = 0
        self.book_count = 0
        self.book_attempt_count = 0
        self.buys.clear()
        self.books.clear()
        self.book_failures.clear()
        self.fail_next_book = False
        self.fail_book_message = "slot_unavailable"


@dataclass
class StubSelfModAdapter:
    """Self-mod apply counter — Hard approve mandatory."""

    apply_count: int = 0
    policy_change_count: int = 0
    applied: list[dict[str, Any]] = field(default_factory=list)

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.apply_count += 1
        result = {"apply_id": f"apply-{self.apply_count}", **payload}
        self.applied.append(result)
        return result

    def policy_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.policy_change_count += 1
        result = {"policy_id": f"pol-{self.policy_change_count}", **payload}
        self.applied.append(result)
        return result

    def reset(self) -> None:
        self.apply_count = 0
        self.policy_change_count = 0
        self.applied.clear()


@dataclass
class CronEmission:
    job_id: str
    payload: dict[str, Any]
    emitted: bool
    reason: str


class StubCronEmitter:
    """Proactive cron emissions — blocked when pause_agent is set (INV-KILL-001)."""

    def __init__(self, kill_switches: _PauseAware) -> None:
        self.kill = kill_switches
        self.emissions: list[CronEmission] = []

    def emit_proactive(self, job_id: str, payload: dict[str, Any] | None = None) -> CronEmission:
        if self.kill.is_paused:
            record = CronEmission(
                job_id=job_id,
                payload=dict(payload or {}),
                emitted=False,
                reason="pause_agent",
            )
            self.emissions.append(record)
            return record
        record = CronEmission(
            job_id=job_id,
            payload=dict(payload or {}),
            emitted=True,
            reason="ok",
        )
        self.emissions.append(record)
        return record

    def emitted_count(self) -> int:
        return sum(1 for e in self.emissions if e.emitted)

    def reset(self) -> None:
        self.emissions.clear()
