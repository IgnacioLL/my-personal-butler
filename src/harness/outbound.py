"""Outbound message catcher — WhatsApp-like outbound capture for harness CI.

Assert against messages that would have left the Gateway, without a live channel.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class OutboundMessage:
    channel: str
    to: str
    body: str
    ts: str
    meta: dict[str, Any] = field(default_factory=dict)


class OutboundMessageCatcher:
    """Spy inbox for outbound WhatsApp (and future channel) sends."""

    def __init__(self) -> None:
        self.messages: list[OutboundMessage] = []

    def send(
        self,
        channel: str,
        to: str,
        body: str,
        *,
        ts: datetime | None = None,
        **meta: Any,
    ) -> OutboundMessage:
        when = ts or datetime.now(timezone.utc)
        msg = OutboundMessage(
            channel=channel,
            to=to,
            body=body,
            ts=when.isoformat(),
            meta=dict(meta),
        )
        self.messages.append(msg)
        return msg

    def clear(self) -> None:
        self.messages.clear()

    def count(self) -> int:
        return len(self.messages)

    def for_recipient(self, to: str) -> list[OutboundMessage]:
        return [m for m in self.messages if m.to == to]

    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(m) for m in self.messages]

    def write_json(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"messages": self.to_list()}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
