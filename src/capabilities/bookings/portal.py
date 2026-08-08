"""Stub Booksy-class portal — deterministic slots; no live network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class PortalSlot:
    id: str
    start: datetime
    end: datetime
    period: str = "any"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "period": self.period,
            "duration_minutes": int((self.end - self.start).total_seconds() // 60),
        }


@dataclass
class StubBooksyPortal:
    """In-memory Booksy double: list availability; book only via commerce adapter.

    Portal itself never mutates reservations — ActionGateway commerce.book is the
    sole execute counter (INV-BOOK-001).
    """

    shop: str = "Main St Barber"
    shop_url: str = "https://stub.booksy.test/main-st-barber"
    service: str = "haircut"
    stylist: str = "Jordan"
    duration_minutes: int = 45
    estimated_price: float = 28.0
    currency: str = "EUR"
    cancellation_policy: str = "Free cancel up to 4 hours before; late cancel may charge 50%."
    slots: list[PortalSlot] = field(default_factory=list)
    list_count: int = 0

    @classmethod
    def from_fixture(cls, path: Path | str) -> "StubBooksyPortal":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        slots: list[PortalSlot] = []
        for raw in data.get("slots") or []:
            slots.append(
                PortalSlot(
                    id=str(raw.get("id") or f"slot-{len(slots)+1}"),
                    start=datetime.fromisoformat(str(raw["start"])),
                    end=datetime.fromisoformat(str(raw["end"])),
                    period=str(raw.get("period") or "any"),
                )
            )
        return cls(
            shop=str(data.get("shop") or "Main St Barber"),
            shop_url=str(data.get("shop_url") or ""),
            service=str(data.get("service") or "haircut"),
            stylist=str(data.get("stylist") or ""),
            duration_minutes=int(data.get("duration_minutes") or 45),
            estimated_price=float(data.get("estimated_price") or 0),
            currency=str(data.get("currency") or "EUR"),
            cancellation_policy=str(data.get("cancellation_policy") or ""),
            slots=slots,
        )

    def list_slots(
        self,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        period: str | None = None,
        limit: int = 3,
    ) -> list[PortalSlot]:
        """Return available slots filtered by window/period (read-only)."""
        self.list_count += 1
        out: list[PortalSlot] = []
        for slot in self.slots:
            if window_start is not None and slot.end <= window_start:
                continue
            if window_end is not None and slot.start >= window_end:
                continue
            if period and period != "any" and slot.period not in {period, "any"}:
                continue
            out.append(slot)
            if len(out) >= limit:
                break
        return out

    def shop_card(self) -> dict[str, Any]:
        return {
            "shop": self.shop,
            "shop_url": self.shop_url,
            "service": self.service,
            "stylist": self.stylist,
            "duration_minutes": self.duration_minutes,
            "estimated_price": self.estimated_price,
            "currency": self.currency,
            "cancellation_policy": self.cancellation_policy,
        }

    def reset_counters(self) -> None:
        self.list_count = 0
