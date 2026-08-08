"""Spend caps — daily/weekly limits for shopping execute (INV-PAY-002).

Caps are checked at execute time. Cap breach blocks buy even with an accepted
approval; raising the cap requires an intentional config change (not chat text).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


@dataclass
class SpendCapConfig:
    """Daily / weekly spend limits (currency units)."""

    daily_limit: float = 50.0
    weekly_limit: float = 150.0
    currency: str = "EUR"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SpendCapConfig":
        raw = data or {}
        return cls(
            daily_limit=float(raw.get("daily_limit", 50.0)),
            weekly_limit=float(raw.get("weekly_limit", 150.0)),
            currency=str(raw.get("currency") or "EUR"),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> "SpendCapConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        caps = data.get("spend_caps") if isinstance(data, dict) else None
        if caps is None and isinstance(data, dict):
            caps = data
        return cls.from_dict(caps if isinstance(caps, dict) else {})


@dataclass
class SpendEntry:
    amount: float
    ts: datetime
    receipt_id: Optional[str] = None
    approval_id: Optional[str] = None
    sku: Optional[str] = None
    merchant: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": self.amount,
            "ts": self.ts.isoformat(),
            "receipt_id": self.receipt_id,
            "approval_id": self.approval_id,
            "sku": self.sku,
            "merchant": self.merchant,
        }


@dataclass
class CapCheckResult:
    ok: bool
    reason: str
    amount: float
    daily_spent: float
    weekly_spent: float
    daily_limit: float
    weekly_limit: float
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SpendLedger:
    """In-memory spend ledger for harness cap math (fake clock aware)."""

    entries: list[SpendEntry] = field(default_factory=list)
    config: SpendCapConfig = field(default_factory=SpendCapConfig)
    rejections: list[dict[str, Any]] = field(default_factory=list)

    def spent_since(self, since: datetime) -> float:
        total = 0.0
        for entry in self.entries:
            ts = entry.ts
            if ts.tzinfo is None and since.tzinfo is not None:
                ts = ts.replace(tzinfo=since.tzinfo)
            elif ts.tzinfo is not None and since.tzinfo is None:
                since = since.replace(tzinfo=ts.tzinfo)
            if ts >= since:
                total += float(entry.amount)
        return total

    def daily_spent(self, now: datetime) -> float:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.spent_since(start)

    def weekly_spent(self, now: datetime) -> float:
        # Rolling 7-day window ending at `now` (inclusive of recent spends).
        start = now - timedelta(days=7)
        return self.spent_since(start)

    def check(self, amount: float, *, now: datetime) -> CapCheckResult:
        amt = float(amount)
        daily = self.daily_spent(now)
        weekly = self.weekly_spent(now)
        daily_limit = float(self.config.daily_limit)
        weekly_limit = float(self.config.weekly_limit)
        if daily + amt > daily_limit:
            return CapCheckResult(
                ok=False,
                reason="spend_cap_daily",
                amount=amt,
                daily_spent=daily,
                weekly_spent=weekly,
                daily_limit=daily_limit,
                weekly_limit=weekly_limit,
                currency=self.config.currency,
            )
        if weekly + amt > weekly_limit:
            return CapCheckResult(
                ok=False,
                reason="spend_cap_weekly",
                amount=amt,
                daily_spent=daily,
                weekly_spent=weekly,
                daily_limit=daily_limit,
                weekly_limit=weekly_limit,
                currency=self.config.currency,
            )
        return CapCheckResult(
            ok=True,
            reason="ok",
            amount=amt,
            daily_spent=daily,
            weekly_spent=weekly,
            daily_limit=daily_limit,
            weekly_limit=weekly_limit,
            currency=self.config.currency,
        )

    def record(
        self,
        amount: float,
        *,
        now: datetime,
        receipt_id: str | None = None,
        approval_id: str | None = None,
        sku: str | None = None,
        merchant: str | None = None,
    ) -> SpendEntry:
        entry = SpendEntry(
            amount=float(amount),
            ts=now,
            receipt_id=receipt_id,
            approval_id=approval_id,
            sku=sku,
            merchant=merchant,
        )
        self.entries.append(entry)
        return entry

    def record_rejection(self, detail: dict[str, Any]) -> dict[str, Any]:
        row = dict(detail)
        self.rejections.append(row)
        return row

    def snapshot(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "entries": [e.to_dict() for e in self.entries],
            "rejections": list(self.rejections),
        }

    def reset(self) -> None:
        self.entries.clear()
        self.rejections.clear()
