"""High-level todo create flow: parse → auto-approve → store → confirm outbound."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from capabilities.todos.parse import ParsedTodo, parse_todo
from capabilities.todos.store import Todo, TodoSource, TodoStore
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalTier, tier_for


@dataclass
class CreateTodoResult:
    ok: bool
    todo: Optional[Todo]
    parsed: Optional[ParsedTodo]
    confirm_body: str
    approval_id: Optional[str]
    tier: str
    reason: str
    deduplicated: bool = False
    gateway_result: Optional[ProposeResult] = None


class TodoService:
    """Create todos from WhatsApp utterances (Auto tier) with dedup."""

    def __init__(
        self,
        store: TodoStore,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        gateway: ActionGateway | None = None,
        recipient: str = "",
    ) -> None:
        self.store = store
        self.clock = clock
        self.catcher = catcher
        self.gateway = gateway
        self.recipient = recipient
        if self.gateway is not None:
            self.gateway.todos = self.store

    def create_from_utterance(
        self,
        utterance: str,
        *,
        recipient: str | None = None,
    ) -> CreateTodoResult:
        to = recipient if recipient is not None else self.recipient
        now = self.clock.now()
        tier = tier_for("todo_add")
        if tier != ApprovalTier.AUTO:
            return CreateTodoResult(
                ok=False,
                todo=None,
                parsed=None,
                confirm_body="",
                approval_id=None,
                tier=tier.value,
                reason=f"expected_auto_tier_got_{tier.value}",
            )

        try:
            parsed = parse_todo(utterance)
        except ValueError as exc:
            return CreateTodoResult(
                ok=False,
                todo=None,
                parsed=None,
                confirm_body="",
                approval_id=None,
                tier=tier.value,
                reason=f"parse_error:{exc}",
            )

        existing = self.store.find_open_duplicate(parsed.title)
        if existing is not None:
            confirm = f"Already on your list: {existing.title}"
            self.catcher.send(
                "whatsapp",
                to or "owner",
                confirm,
                ts=now,
                kind="todo_dedup",
                todo_id=existing.id,
            )
            return CreateTodoResult(
                ok=True,
                todo=existing,
                parsed=parsed,
                confirm_body=confirm,
                approval_id=None,
                tier=tier.value,
                reason="deduplicated",
                deduplicated=True,
            )

        payload: dict[str, Any] = {
            "title": parsed.title,
            "created_from": TodoSource.WHATSAPP.value,
            "recipient": to,
        }

        gw_result: ProposeResult | None = None
        todo: Todo | None = None

        if self.gateway is not None:
            gw_result = self.gateway.propose(
                "todo_add",
                f"Add todo: {parsed.title}",
                payload,
            )
            if not gw_result.ok or not gw_result.executed:
                return CreateTodoResult(
                    ok=False,
                    todo=None,
                    parsed=parsed,
                    confirm_body="",
                    approval_id=gw_result.approval_id,
                    tier=gw_result.tier or tier.value,
                    reason=gw_result.reason,
                    gateway_result=gw_result,
                )
            if gw_result.approval_id is not None:
                return CreateTodoResult(
                    ok=False,
                    todo=None,
                    parsed=parsed,
                    confirm_body="",
                    approval_id=gw_result.approval_id,
                    tier=gw_result.tier or tier.value,
                    reason="unexpected_approval_item_for_auto",
                    gateway_result=gw_result,
                )
            auto = gw_result.auto_result or {}
            todo_id = auto.get("todo_id")
            todo = self.store.get(todo_id) if todo_id else None
            if todo is None:
                return CreateTodoResult(
                    ok=False,
                    todo=None,
                    parsed=parsed,
                    confirm_body="",
                    approval_id=None,
                    tier=tier.value,
                    reason="gateway_auto_missing_todo",
                    gateway_result=gw_result,
                )
        else:
            todo = self.store.create(
                title=parsed.title,
                created_at=now,
                created_from=TodoSource.WHATSAPP,
            )

        confirm = f"Added to your list: {todo.title}"
        self.catcher.send(
            "whatsapp",
            to or "owner",
            confirm,
            ts=now,
            kind="todo_confirm",
            todo_id=todo.id,
        )
        return CreateTodoResult(
            ok=True,
            todo=todo,
            parsed=parsed,
            confirm_body=confirm,
            approval_id=None,
            tier=tier.value,
            reason="created",
            gateway_result=gw_result,
        )
