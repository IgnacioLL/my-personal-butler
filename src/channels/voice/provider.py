"""Mock outbound voice/call provider for harness CI.

Places calls, records mid-call tool invocations against the call-mode
allowlist (INV-APPR-005), and queues an after-call WhatsApp summary.
No live Twilio/Telnyx — counters and catcher only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from channels.voice.allowlist import (
    CALL_MODE_ALLOWED_TOOLS,
    CALL_MODE_FORBIDDEN_TOOLS,
    call_mode_block_reason,
)
from harness.clock import FakeClock
from harness.outbound import OutboundMessage, OutboundMessageCatcher


@dataclass
class ToolInvocation:
    tool: str
    allowed: bool
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    ts: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "allowed": self.allowed,
            "reason": self.reason,
            "payload": dict(self.payload),
            "result": self.result,
            "ts": self.ts,
        }


@dataclass
class CallSession:
    id: str
    to: str
    script: str
    status: str  # ringing | active | ended
    started_at: datetime
    tool_invocations: list[ToolInvocation] = field(default_factory=list)
    ended_at: Optional[datetime] = None
    reminder_id: Optional[str] = None
    habit_id: Optional[str] = None
    outcome: Optional[str] = None
    summary_body: Optional[str] = None
    summary_queued: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "to": self.to,
            "script": self.script,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "reminder_id": self.reminder_id,
            "habit_id": self.habit_id,
            "outcome": self.outcome,
            "summary_body": self.summary_body,
            "summary_queued": self.summary_queued,
            "tool_invocations": [t.to_dict() for t in self.tool_invocations],
            "meta": dict(self.meta),
        }


@dataclass
class ToolInvokeResult:
    ok: bool
    reason: str
    invocation: ToolInvocation
    session_id: str


class MockVoiceProvider:
    """Harness double for outbound voice calls + call-mode tool gate."""

    def __init__(
        self,
        catcher: OutboundMessageCatcher,
        clock: FakeClock,
        *,
        default_to: str = "",
    ) -> None:
        self.catcher = catcher
        self.clock = clock
        self.default_to = default_to
        self.calls: list[CallSession] = []
        self._by_id: dict[str, CallSession] = {}

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def active_count(self) -> int:
        return sum(1 for c in self.calls if c.status == "active")

    def place_call(
        self,
        *,
        to: str | None = None,
        script: str,
        reminder_id: str | None = None,
        habit_id: str | None = None,
        auto_answer: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> CallSession:
        """Place an outbound call. Records the session; no live telephony."""
        now = self.clock.now()
        recipient = to or self.default_to or "owner"
        session = CallSession(
            id=f"call-{uuid4().hex[:12]}",
            to=recipient,
            script=script,
            status="ringing",
            started_at=now,
            reminder_id=reminder_id,
            habit_id=habit_id,
            meta=dict(meta or {}),
        )
        if auto_answer:
            session.status = "active"
        self.calls.append(session)
        self._by_id[session.id] = session
        # Mirror call placement on outbound catcher for channel-touch ordering.
        self.catcher.send(
            "call",
            recipient,
            script,
            ts=now,
            kind="outbound_call",
            call_id=session.id,
            reminder_id=reminder_id,
            habit_id=habit_id,
        )
        return session

    def get(self, call_id: str) -> Optional[CallSession]:
        return self._by_id.get(call_id)

    def invoke_tool(
        self,
        call_id: str,
        tool: str,
        payload: dict[str, Any] | None = None,
    ) -> ToolInvokeResult:
        """Attempt a mid-call tool. Hard actions are fail-closed (INV-APPR-005)."""
        session = self._by_id.get(call_id)
        if session is None:
            inv = ToolInvocation(
                tool=tool,
                allowed=False,
                reason="unknown_call",
                payload=dict(payload or {}),
            )
            return ToolInvokeResult(
                ok=False, reason="unknown_call", invocation=inv, session_id=call_id
            )
        if session.status != "active":
            inv = ToolInvocation(
                tool=tool,
                allowed=False,
                reason=f"call_not_active:{session.status}",
                payload=dict(payload or {}),
                ts=self.clock.now().isoformat(),
            )
            session.tool_invocations.append(inv)
            return ToolInvokeResult(
                ok=False,
                reason=inv.reason,
                invocation=inv,
                session_id=call_id,
            )

        block = call_mode_block_reason(tool)
        if block is not None:
            inv = ToolInvocation(
                tool=tool,
                allowed=False,
                reason=block,
                payload=dict(payload or {}),
                ts=self.clock.now().isoformat(),
            )
            session.tool_invocations.append(inv)
            return ToolInvokeResult(
                ok=False, reason=block, invocation=inv, session_id=call_id
            )

        result_payload = {
            "stub": True,
            "tool": tool,
            "payload": dict(payload or {}),
            "call_id": call_id,
        }
        inv = ToolInvocation(
            tool=tool,
            allowed=True,
            reason="ok",
            payload=dict(payload or {}),
            result=result_payload,
            ts=self.clock.now().isoformat(),
        )
        session.tool_invocations.append(inv)
        return ToolInvokeResult(
            ok=True, reason="ok", invocation=inv, session_id=call_id
        )

    def end_call(
        self,
        call_id: str,
        *,
        outcome: str = "completed",
        queue_whatsapp_summary: bool = True,
    ) -> CallSession:
        """End call and optionally queue an after-call WhatsApp summary."""
        session = self._by_id.get(call_id)
        if session is None:
            raise KeyError(f"unknown call_id: {call_id}")
        if session.status == "ended":
            return session

        now = self.clock.now()
        session.status = "ended"
        session.ended_at = now
        session.outcome = outcome
        session.summary_body = self._format_summary(session)

        if queue_whatsapp_summary:
            msg = self._queue_summary(session)
            session.summary_queued = True
            session.meta["summary_outbound_ts"] = msg.ts
        return session

    def place_and_complete(
        self,
        *,
        to: str | None = None,
        script: str,
        reminder_id: str | None = None,
        habit_id: str | None = None,
        outcome: str = "reminder_delivered",
        meta: dict[str, Any] | None = None,
    ) -> CallSession:
        """Convenience: place call, end it, queue WhatsApp summary."""
        session = self.place_call(
            to=to,
            script=script,
            reminder_id=reminder_id,
            habit_id=habit_id,
            meta=meta,
        )
        return self.end_call(session.id, outcome=outcome)

    def forbidden_attempts(self) -> list[ToolInvocation]:
        """All mid-call attempts at buy/book/self_mod_apply (for INV assertions)."""
        out: list[ToolInvocation] = []
        for call in self.calls:
            for inv in call.tool_invocations:
                if inv.tool in CALL_MODE_FORBIDDEN_TOOLS:
                    out.append(inv)
        return out

    def snapshot(self) -> dict[str, Any]:
        return {
            "call_count": self.call_count,
            "active_count": self.active_count,
            "allowed_tools": sorted(CALL_MODE_ALLOWED_TOOLS),
            "forbidden_tools": sorted(CALL_MODE_FORBIDDEN_TOOLS),
            "calls": [c.to_dict() for c in self.calls],
        }

    def reset(self) -> None:
        self.calls.clear()
        self._by_id.clear()

    def _format_summary(self, session: CallSession) -> str:
        topic = session.script
        if topic.lower().startswith("calling about:"):
            topic = topic.split(":", 1)[1].strip()
        outcome = session.outcome or "completed"
        return (
            f"Call summary: spoke about '{topic}' "
            f"(outcome={outcome}, call_id={session.id})."
        )

    def _queue_summary(self, session: CallSession) -> OutboundMessage:
        assert session.summary_body is not None
        return self.catcher.send(
            "whatsapp",
            session.to,
            session.summary_body,
            ts=session.ended_at or self.clock.now(),
            kind="after_call_summary",
            call_id=session.id,
            reminder_id=session.reminder_id,
            habit_id=session.habit_id,
            outcome=session.outcome,
        )
