"""Stub adapters for gated side effects (calendar, buy, book, self-mod, cron).

No live services — counters for INV assertions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class _PauseAware(Protocol):
    @property
    def is_paused(self) -> bool: ...


@dataclass
class StubCalendarAdapter:
    """In-memory calendar — create/modify must only be called after soft confirm."""

    events: list[dict[str, Any]] = field(default_factory=list)
    create_count: int = 0
    modify_count: int = 0
    cancel_count: int = 0

    def create(self, event: dict[str, Any]) -> dict[str, Any]:
        self.create_count += 1
        stored = dict(event)
        stored.setdefault("id", f"evt-{self.create_count}")
        self.events.append(stored)
        return stored

    def modify(self, event_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.modify_count += 1
        for evt in self.events:
            if evt.get("id") == event_id:
                evt.update(patch)
                return evt
        updated = {"id": event_id, **patch}
        self.events.append(updated)
        return updated

    def cancel(self, event_id: str) -> bool:
        self.cancel_count += 1
        before = len(self.events)
        self.events = [e for e in self.events if e.get("id") != event_id]
        return len(self.events) < before

    def reset(self) -> None:
        self.events.clear()
        self.create_count = 0
        self.modify_count = 0
        self.cancel_count = 0


@dataclass
class StubCommerceAdapter:
    """Buy / book execute counters — must stay 0 until Accept."""

    buy_count: int = 0
    book_count: int = 0
    buys: list[dict[str, Any]] = field(default_factory=list)
    books: list[dict[str, Any]] = field(default_factory=list)

    def buy(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.buy_count += 1
        receipt = {"receipt_id": f"buy-{self.buy_count}", **payload}
        self.buys.append(receipt)
        return receipt

    def book(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.book_count += 1
        confirmation = {"booking_id": f"book-{self.book_count}", **payload}
        self.books.append(confirmation)
        return confirmation

    def reset(self) -> None:
        self.buy_count = 0
        self.book_count = 0
        self.buys.clear()
        self.books.clear()


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
