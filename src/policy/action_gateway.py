"""Action gateway — propose / accept / deny / execute with approval gates.

Hard actions (buy, book, self_mod_apply, policy_change) cannot execute unless
approval.status == accepted. Soft calendar writes are likewise gated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from capabilities.reminders.store import ReminderKind, ReminderStore
from capabilities.todos.store import TodoSource, TodoStore
from capabilities.bookings.store import BookingStore
from harness.adapters import (
    StubCalendarAdapter,
    StubCommerceAdapter,
    StubCronEmitter,
    StubSelfModAdapter,
)
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.approvals import (
    HARD_ACTION_TYPES,
    ApprovalError,
    ApprovalStatus,
    ApprovalStore,
    ApprovalTier,
    is_hard_action,
    tier_for,
)
from policy.audit import AuditLog
from policy.kill_switches import KillSwitches


@dataclass
class ExecuteResult:
    ok: bool
    reason: str
    approval_id: Optional[str] = None
    result: Any = None
    audit_id: Optional[str] = None


@dataclass
class ProposeResult:
    ok: bool
    reason: str
    approval_id: Optional[str] = None
    tier: Optional[str] = None
    auto_result: Any = None
    executed: bool = False


@dataclass
class ActionGateway:
    """Single entry for gated side effects used by INV-* contract tests."""

    clock: FakeClock
    approvals_path: Path | str | None = None
    approvals: ApprovalStore = field(init=False)
    kill: KillSwitches = field(default_factory=KillSwitches)
    audit: AuditLog = field(init=False)
    calendar: StubCalendarAdapter = field(default_factory=StubCalendarAdapter)
    commerce: StubCommerceAdapter = field(default_factory=StubCommerceAdapter)
    selfmod: StubSelfModAdapter = field(default_factory=StubSelfModAdapter)
    reminders: ReminderStore | None = None
    todos: TodoStore | None = None
    bookings: BookingStore | None = None
    outbound: OutboundMessageCatcher | None = None
    cron: StubCronEmitter = field(init=False)
    execute_attempts: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.approvals = ApprovalStore(self.clock, persist_path=self.approvals_path)
        self.audit = AuditLog(self.clock)
        self.cron = StubCronEmitter(self.kill)
        if self.reminders is None:
            self.reminders = ReminderStore()
        if self.todos is None:
            self.todos = TodoStore()

    def attach_bookings(
        self,
        store: BookingStore,
        *,
        outbound: OutboundMessageCatcher | None = None,
    ) -> None:
        """Wire booking task store + optional WhatsApp catcher for writeback/confirm."""
        self.bookings = store
        if outbound is not None:
            self.outbound = outbound

    # --- Kill switches -------------------------------------------------

    def pause_agent(self) -> None:
        self.kill.pause()

    def resume_agent(self) -> None:
        self.kill.resume()

    def freeze_spending(self) -> None:
        self.kill.freeze_spending()

    def freeze_self_mod(self) -> None:
        self.kill.freeze_self_mod()

    def cancel_pending(self) -> list[str]:
        cancelled = self.approvals.cancel_pending()
        return [c.id for c in cancelled]

    # --- Propose / decide ----------------------------------------------

    def propose(
        self,
        action_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        *,
        expires_in: timedelta | None = None,
        **kwargs: Any,
    ) -> ProposeResult:
        tier = tier_for(action_type)
        if tier == ApprovalTier.FORBIDDEN:
            return ProposeResult(
                ok=False,
                reason="forbidden",
                tier=tier.value,
            )

        if tier == ApprovalTier.AUTO:
            result = self._run_adapter(action_type, payload or {})
            # Auto side effects are not approval-gated; still audit without approval id.
            self.audit.record(
                action_type,
                approval_id=None,
                success=True,
                detail={"tier": "auto", "result": result},
            )
            return ProposeResult(
                ok=True,
                reason="auto_executed",
                tier=tier.value,
                auto_result=result,
                executed=True,
            )

        item = self.approvals.create(
            action_type,
            summary,
            payload,
            expires_in=expires_in,
            **kwargs,
        )
        return ProposeResult(
            ok=True,
            reason="pending_approval",
            approval_id=item.id,
            tier=tier.value,
            executed=False,
        )

    def accept(self, approval_id: str) -> Any:
        return self.approvals.accept(approval_id)

    def deny(self, approval_id: str) -> Any:
        return self.approvals.deny(approval_id)

    def edit(
        self,
        approval_id: str,
        *,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
        payload_patch: dict[str, Any] | None = None,
        estimated_cost: float | None = None,
    ) -> Any:
        """Edit pending approval details (same surface Android Edit uses)."""
        return self.approvals.edit(
            approval_id,
            summary=summary,
            payload=payload,
            payload_patch=payload_patch,
            estimated_cost=estimated_cost,
        )

    # --- Execute (gated) -----------------------------------------------

    def execute(self, approval_id: str) -> ExecuteResult:
        """Execute only when approval.status == accepted (and not kill-blocked)."""
        self.approvals.expire_due()
        item = self.approvals.get(approval_id)
        attempt = {
            "approval_id": approval_id,
            "action_type": item.action_type if item else None,
            "status_before": item.status.value if item else None,
        }
        self.execute_attempts.append(attempt)

        if item is None:
            return ExecuteResult(ok=False, reason="not_found", approval_id=approval_id)

        if item.status != ApprovalStatus.ACCEPTED:
            return ExecuteResult(
                ok=False,
                reason=f"status={item.status.value}",
                approval_id=approval_id,
            )

        blocked, block_reason = self.kill.blocks_execute(item.action_type)
        if blocked:
            return ExecuteResult(
                ok=False,
                reason=block_reason,
                approval_id=approval_id,
            )

        try:
            adapter_result = self._run_adapter(item.action_type, item.payload)
            self.approvals.mark_executed(approval_id)
            audit = self.audit.record(
                item.action_type,
                approval_id=approval_id,
                success=True,
                detail={"result": adapter_result},
            )
            return ExecuteResult(
                ok=True,
                reason="executed",
                approval_id=approval_id,
                result=adapter_result,
                audit_id=audit.id,
            )
        except Exception as exc:  # noqa: BLE001
            # INV-BOOK-002: failed book must not leave user-facing success.
            if item.action_type == "book":
                self._mark_booking_failed(item.payload, str(exc))
            self.approvals.mark_failed(approval_id, str(exc))
            self.audit.record(
                item.action_type,
                approval_id=approval_id,
                success=False,
                detail={"error": str(exc)},
            )
            return ExecuteResult(
                ok=False,
                reason=f"failed:{exc}",
                approval_id=approval_id,
            )

    def try_hard_action_without_approval(
        self,
        action_type: str,
        payload: dict[str, Any] | None = None,
    ) -> ExecuteResult:
        """Policy layer: hard actions cannot bypass the approval gate.

        Models/skills that try to call execute adapters directly are blocked.
        """
        if not is_hard_action(action_type) and action_type not in HARD_ACTION_TYPES:
            # Soft/auto may still go through propose; this helper is for hard-path abuse.
            pass
        if is_hard_action(action_type):
            self.execute_attempts.append(
                {
                    "approval_id": None,
                    "action_type": action_type,
                    "status_before": None,
                    "bypass_attempt": True,
                }
            )
            return ExecuteResult(
                ok=False,
                reason="hard_action_requires_accepted_approval",
                approval_id=None,
            )
        # Soft path without approval also blocked at this entry.
        if tier_for(action_type) == ApprovalTier.SOFT_CONFIRM:
            return ExecuteResult(
                ok=False,
                reason="soft_action_requires_accepted_approval",
                approval_id=None,
            )
        return ExecuteResult(ok=False, reason="unsupported", approval_id=None)

    def _run_adapter(self, action_type: str, payload: dict[str, Any]) -> Any:
        if action_type == "buy":
            return self.commerce.buy(payload)
        if action_type == "book":
            return self._execute_book(payload)
        if action_type == "self_mod_apply":
            return self.selfmod.apply(payload)
        if action_type == "policy_change":
            return self.selfmod.policy_change(payload)
        if action_type == "calendar_create":
            return self.calendar.create(payload)
        if action_type == "calendar_modify":
            return self.calendar.modify(payload.get("id", ""), payload)
        if action_type == "calendar_cancel":
            return self.calendar.cancel(payload.get("id", ""))
        if action_type == "reminder_create":
            return self._create_reminder(payload)
        if action_type == "habit_create":
            return self._create_habit(payload)
        if action_type == "todo_add":
            return self._add_todo(payload)
        if action_type == "todo_complete":
            return self._complete_todo(payload)
        if action_type in {
            "diet_draft",
            "whatsapp_reply",
            "calendar_read",
            "memory_read",
            "todo_read",
            "source_read",
            "memory_update",
            "self_mod_propose",
        }:
            return {"stub": True, "action_type": action_type, "payload": payload}
        raise ApprovalError("unknown_adapter", f"no adapter for {action_type!r}")

    def _resolve_book_slot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Resolve start/end from chosen_slot_index + options when present."""
        resolved = dict(payload)
        options = list(payload.get("options") or [])
        if options:
            idx = int(payload.get("chosen_slot_index") or 0)
            idx = max(0, min(idx, len(options) - 1))
            chosen = dict(options[idx])
            resolved["chosen_slot_index"] = idx
            resolved["start"] = chosen.get("start") or payload.get("start")
            resolved["end"] = chosen.get("end") or payload.get("end")
            resolved["slot_id"] = chosen.get("id") or payload.get("slot_id")
            if chosen.get("stylist"):
                resolved.setdefault("stylist", chosen["stylist"])
        return resolved

    def _execute_book(self, payload: dict[str, Any]) -> Any:
        """Book after Accept: portal execute + calendar writeback + WhatsApp confirm.

        Failure path raises before writeback/confirm so INV-BOOK-002 holds.
        """
        resolved = self._resolve_book_slot(payload)
        start = resolved.get("start")
        end = resolved.get("end")
        if not start or not end:
            raise ApprovalError("invalid_payload", "book requires start and end")

        # Commerce book first — must succeed before any success side effects.
        confirmation = self.commerce.book(resolved)

        title = str(
            resolved.get("calendar_title")
            or f"{resolved.get('service', 'booking')} @ {resolved.get('shop', 'shop')}"
        )
        event_payload: dict[str, Any] = {
            "title": title,
            "start": start,
            "end": end,
            "timezone": resolved.get("timezone") or "UTC",
            "location": str(resolved.get("shop") or ""),
            "meta": {
                "booking_id": confirmation.get("booking_id"),
                "source": "booksy_stub",
                "slot_id": resolved.get("slot_id"),
                "booking_task_id": resolved.get("booking_task_id"),
            },
        }
        cal_event = self.calendar.create(event_payload)
        confirmation["calendar_event"] = cal_event

        task_id = resolved.get("booking_task_id")
        if self.bookings is not None and task_id:
            self.bookings.mark_booked(
                str(task_id),
                booking_id=str(confirmation.get("booking_id")),
                calendar_event_id=str(cal_event.get("id") or ""),
                at=self.clock.now(),
            )

        if self.outbound is not None:
            when = datetime.fromisoformat(str(start))
            end_dt = datetime.fromisoformat(str(end))
            price = resolved.get("estimated_price")
            currency = resolved.get("currency") or ""
            price_bit = f" (~{price:g} {currency})" if price is not None else ""
            body = (
                f"Booked: {title} on {when.strftime('%A %Y-%m-%d %H:%M')}–"
                f"{end_dt.strftime('%H:%M')}{price_bit}. "
                f"Confirmation {confirmation.get('booking_id')}."
            )
            self.outbound.send(
                "whatsapp",
                str(resolved.get("recipient") or "owner"),
                body,
                ts=self.clock.now(),
                kind="booking_confirm",
                approval_id=None,
                booking_id=confirmation.get("booking_id"),
                booking_task_id=task_id,
                calendar_event_id=cal_event.get("id"),
            )

        return confirmation

    def _mark_booking_failed(self, payload: dict[str, Any], error: str) -> None:
        task_id = (payload or {}).get("booking_task_id")
        if self.bookings is None or not task_id:
            return
        try:
            self.bookings.mark_failed(str(task_id), error, at=self.clock.now())
        except KeyError:
            return

    def _parse_due(self, payload: dict[str, Any], *, action: str) -> datetime:
        due_raw = payload.get("due_at")
        if not due_raw:
            raise ApprovalError("invalid_payload", f"{action} requires due_at")
        if isinstance(due_raw, datetime):
            return due_raw
        return datetime.fromisoformat(str(due_raw))

    def _create_reminder(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.reminders is not None
        due_at = self._parse_due(payload, action="reminder_create")
        rem = self.reminders.create(
            text=str(payload.get("text") or ""),
            timezone=str(payload.get("timezone") or "UTC"),
            kind=ReminderKind(payload.get("kind") or ReminderKind.ONE_SHOT.value),
            due_at=due_at,
            created_at=self.clock.now(),
            hour=int(payload.get("hour") if payload.get("hour") is not None else due_at.hour),
            minute=int(
                payload.get("minute") if payload.get("minute") is not None else due_at.minute
            ),
            weekday=payload.get("weekday"),
            recipient=str(payload.get("recipient") or ""),
            meta=dict(payload.get("meta") or {}),
        )
        return {"reminder_id": rem.id, "due_at": rem.due_at.isoformat(), "kind": rem.kind.value}

    def _add_todo(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.todos is not None
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ApprovalError("invalid_payload", "todo_add requires title")
        created_from = payload.get("created_from") or TodoSource.AGENT.value
        existing = self.todos.find_open_duplicate(title)
        if existing is not None:
            return {
                "todo_id": existing.id,
                "title": existing.title,
                "status": existing.status.value,
                "deduplicated": True,
            }
        todo = self.todos.create(
            title=title,
            created_at=self.clock.now(),
            created_from=str(created_from),
            notes=str(payload.get("notes") or ""),
            tags=list(payload.get("tags") or []),
        )
        return {
            "todo_id": todo.id,
            "title": todo.title,
            "status": todo.status.value,
            "deduplicated": False,
        }

    def _complete_todo(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.todos is not None
        todo_id = str(payload.get("todo_id") or "")
        if not todo_id:
            raise ApprovalError("invalid_payload", "todo_complete requires todo_id")
        completed_from = payload.get("completed_from") or TodoSource.ANDROID.value
        todo = self.todos.complete(
            todo_id,
            completed_at=self.clock.now(),
            completed_from=str(completed_from),
        )
        return {
            "todo_id": todo.id,
            "title": todo.title,
            "status": todo.status.value,
        }

    def _create_habit(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.reminders is not None
        due_at = self._parse_due(payload, action="habit_create")
        weekday = payload.get("weekday")
        if weekday is None:
            raise ApprovalError("invalid_payload", "habit_create requires weekday")
        habit, rem = self.reminders.create_habit(
            title=str(payload.get("text") or payload.get("title") or ""),
            timezone=str(payload.get("timezone") or "UTC"),
            weekday=int(weekday),
            hour=int(payload.get("hour") if payload.get("hour") is not None else due_at.hour),
            minute=int(
                payload.get("minute") if payload.get("minute") is not None else due_at.minute
            ),
            due_at=due_at,
            created_at=self.clock.now(),
            priority=str(payload.get("habit_priority") or payload.get("priority") or "normal"),
            escalation_enabled=bool(payload.get("escalation_enabled")),
            recipient=str(payload.get("recipient") or ""),
        )
        return {
            "habit_id": habit.id,
            "reminder_id": rem.id,
            "due_at": rem.due_at.isoformat(),
            "escalation_step": habit.escalation_step,
        }
