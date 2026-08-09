"""Production voice provider — outbound allowlist + INV-APPR-005 + after-call WA.

Live Twilio/Telnyx placement is owned by the OpenClaw voice-call plugin.
This adapter:

- enforces the operator outbound allowlist before placing a call
- reuses :class:`MockVoiceProvider` session/tool/summary semantics for CI
- refuses to dial when ``provider`` is live but credentials are incomplete
- never performs carrier HTTP (no SDK installs; CI stays mock)

``build_voice_provider`` returns a mock-backed provider suitable for harness
and for dry-run validation of production config.
"""

from __future__ import annotations

from typing import Any, Optional

from channels.voice.config import VoiceCallConfig, harness_mock_config
from channels.voice.provider import CallSession, MockVoiceProvider, ToolInvokeResult
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher


class ProductionVoiceProvider:
    """Config-backed outbound voice provider with call-mode + after-call summary."""

    def __init__(
        self,
        catcher: OutboundMessageCatcher,
        clock: FakeClock,
        config: VoiceCallConfig,
        *,
        allow_live: bool = False,
    ) -> None:
        self.config = config
        self.allow_live = allow_live
        default_to = config.to_number or ""
        self._inner = MockVoiceProvider(catcher, clock, default_to=default_to)
        self.catcher = catcher
        self.clock = clock
        self.rejected_outbound: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return self._inner.call_count

    @property
    def active_count(self) -> int:
        return self._inner.active_count

    @property
    def calls(self) -> list[CallSession]:
        return self._inner.calls

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
        recipient = (to or self.config.to_number or self._inner.default_to or "").strip()
        if not self.config.outbound_allowed(recipient):
            self.rejected_outbound.append(
                {
                    "to": recipient,
                    "reason": "outbound_not_allowlisted",
                    "script": script,
                }
            )
            raise PermissionError(
                f"outbound_not_allowlisted: {recipient!r} not in "
                f"{sorted(self.config.outbound_allowlist)}"
            )

        if self.config.is_live() and not self.allow_live:
            missing = self.config.missing_live_credentials()
            # Even with complete credentials, this Python harness never dials
            # a live carrier (no SDK / no network). Production dials go through
            # OpenClaw @openclaw/voice-call. We still validate allowlist + policy
            # via the mock session path.
            meta = {
                **dict(meta or {}),
                "production_provider": self.config.provider,
                "live_dial": False,
                "live_via": "openclaw_voice_call_plugin",
                "credentials_complete": not missing,
                "missing_credentials": missing,
            }

        session = self._inner.place_call(
            to=recipient,
            script=script,
            reminder_id=reminder_id,
            habit_id=habit_id,
            auto_answer=auto_answer,
            meta=meta,
        )
        session.meta.setdefault("provider", self.config.provider)
        session.meta.setdefault("from_number", self.config.from_number)
        return session

    def get(self, call_id: str) -> Optional[CallSession]:
        return self._inner.get(call_id)

    def invoke_tool(
        self,
        call_id: str,
        tool: str,
        payload: dict[str, Any] | None = None,
    ) -> ToolInvokeResult:
        return self._inner.invoke_tool(call_id, tool, payload)

    def end_call(
        self,
        call_id: str,
        *,
        outcome: str = "completed",
        queue_whatsapp_summary: bool | None = None,
    ) -> CallSession:
        queue = (
            self.config.after_call_whatsapp_summary
            if queue_whatsapp_summary is None
            else queue_whatsapp_summary
        )
        return self._inner.end_call(
            call_id, outcome=outcome, queue_whatsapp_summary=queue
        )

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
        session = self.place_call(
            to=to,
            script=script,
            reminder_id=reminder_id,
            habit_id=habit_id,
            meta=meta,
        )
        return self.end_call(session.id, outcome=outcome)

    def forbidden_attempts(self):
        return self._inner.forbidden_attempts()

    def snapshot(self) -> dict[str, Any]:
        snap = self._inner.snapshot()
        snap["config"] = self.config.to_dict()
        snap["rejected_outbound"] = list(self.rejected_outbound)
        return snap

    def reset(self) -> None:
        self._inner.reset()
        self.rejected_outbound.clear()


def build_voice_provider(
    catcher: OutboundMessageCatcher,
    clock: FakeClock,
    config: VoiceCallConfig | None = None,
    *,
    allow_live: bool = False,
) -> ProductionVoiceProvider:
    """Factory used by production wiring and CI (defaults to harness mock config)."""
    cfg = config or harness_mock_config()
    if cfg.provider != "mock" and not allow_live:
        # CI / dry-run: keep provider label but never dial.
        pass
    return ProductionVoiceProvider(
        catcher, clock, cfg, allow_live=allow_live
    )
