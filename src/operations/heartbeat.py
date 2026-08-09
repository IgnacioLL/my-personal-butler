"""Morning brief / weekly review heartbeat stubs (Phase 8).

Respects pause_agent kill switch and quiet hours from the memory profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway
from policy.quiet_hours import blocks_proactive, normalize_quiet_config
from intelligence.memory.store import MemoryStore


@dataclass
class HeartbeatResult:
    job_id: str
    emitted: bool
    reason: str
    body: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "emitted": self.emitted,
            "reason": self.reason,
            "body": self.body,
            "meta": dict(self.meta),
        }


class HeartbeatService:
    """Cheap structured proactive jobs — cron/heartbeat double for harness."""

    def __init__(
        self,
        gateway: ActionGateway,
        catcher: OutboundMessageCatcher,
        *,
        memory: MemoryStore | None = None,
        timezone: str = "Europe/Madrid",
        recipient: str = "+15550001111",
        quiet_hours: dict[str, Any] | None = None,
    ) -> None:
        self.gateway = gateway
        self.catcher = catcher
        self.memory = memory
        self.timezone = timezone
        self.recipient = recipient
        self._quiet_override = quiet_hours

    def _quiet_config(self) -> dict[str, Any]:
        if self._quiet_override is not None:
            return normalize_quiet_config(self._quiet_override)
        if self.memory is not None:
            prefs = self.memory.load_hot_profile().get("preferences") or {}
            return normalize_quiet_config(prefs.get("quiet_hours"))
        return {"enabled": False}

    def _guard_proactive(self, job_id: str) -> Optional[HeartbeatResult]:
        if self.gateway.kill.is_paused:
            self.gateway.cron.emit_proactive(job_id, {"kind": "heartbeat"})
            return HeartbeatResult(job_id=job_id, emitted=False, reason="pause_agent")

        blocked, reason = blocks_proactive(
            self.gateway.clock.now(),
            self._quiet_config(),
            timezone=self.timezone,
        )
        if blocked:
            self.gateway.cron.emit_proactive(job_id, {"kind": "heartbeat"})
            return HeartbeatResult(job_id=job_id, emitted=False, reason=reason)
        return None

    def maybe_morning_brief(self) -> HeartbeatResult:
        """Emit a compact morning brief when policy allows."""
        job_id = "morning_brief"
        blocked = self._guard_proactive(job_id)
        if blocked is not None:
            return blocked

        hot = self.memory.load_hot_profile() if self.memory is not None else {}
        identity = hot.get("identity") or {}
        name = identity.get("name") or "there"
        body = (
            f"Good morning, {name}. "
            "Today: check calendar, todos, and pending approvals. "
            "Reply if you want a deeper plan."
        )
        emission = self.gateway.cron.emit_proactive(
            job_id,
            {"kind": "heartbeat", "brief": "morning"},
        )
        if emission.emitted:
            self.catcher.send(
                "whatsapp",
                self.recipient,
                body,
                kind="morning_brief",
                job_id=job_id,
            )
        return HeartbeatResult(
            job_id=job_id,
            emitted=emission.emitted,
            reason=emission.reason,
            body=body if emission.emitted else None,
            meta={"cron": emission.payload},
        )

    def maybe_weekly_review(self) -> HeartbeatResult:
        """Lightweight memory hygiene nudge — weekly ritual stub."""
        job_id = "weekly_review"
        blocked = self._guard_proactive(job_id)
        if blocked is not None:
            return blocked

        body = (
            "Weekly review: skim episodic notes, drop stale prefs, "
            "and confirm quiet hours still match your routine."
        )
        emission = self.gateway.cron.emit_proactive(
            job_id,
            {"kind": "heartbeat", "brief": "weekly_review"},
        )
        if emission.emitted:
            self.catcher.send(
                "whatsapp",
                self.recipient,
                body,
                kind="weekly_review",
                job_id=job_id,
            )
        return HeartbeatResult(
            job_id=job_id,
            emitted=emission.emitted,
            reason=emission.reason,
            body=body if emission.emitted else None,
            meta={"cron": emission.payload},
        )


__all__ = ["HeartbeatResult", "HeartbeatService"]
