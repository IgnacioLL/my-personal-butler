"""Virtual User — scripted client that drives the Gateway like a real user.

Per agent-plan/testing/harnesses-and-fixtures.md:
  inject text/audio → advance fake clock → read state (reminders, approvals, outbound)

No live WhatsApp. Used by gate-tagged E2E flows (E2E-01 first).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from capabilities.reminders.parse import parse_reminder
from capabilities.reminders.service import ReminderService
from capabilities.reminders.store import ReminderStore
from capabilities.todos.parse import looks_like_todo_add
from capabilities.todos.service import TodoService
from capabilities.todos.store import TodoStatus, TodoStore
from channels.android.approvals import AcceptResult, AndroidApprovalInboxApi, ApprovalProjection
from channels.android.projection import AndroidProjectionApi
from harness.artifacts import write_report
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from harness.whatsapp_transport import (
    InboundWhatsAppMessage,
    MockWhatsAppTransport,
    TransportTurnResult,
    default_agent_handler,
)
from intelligence.transcription.pipeline import TranscriptionPipeline
from intelligence.transcription.tts import TtsMode
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalStatus, ApprovalTier, is_hard_action, tier_for

ROOT = Path(__file__).resolve().parents[2]

_REMIND_INTENT = re.compile(
    r"(?:\[Audio\]\s*)?remind\s+me\b",
    re.IGNORECASE,
)

EXPECTED_E2E03_UTTERANCE = "Add todo: buy oat milk."

EXPECTED_E2E01_TRANSCRIPT = "Remind me Sunday at 18:00 to call grandma."
E2E01_AUDIO_FIXTURE = "fx-reminder"


def _looks_like_reminder(body: str) -> bool:
    return bool(_REMIND_INTENT.search(body or ""))


@dataclass
class E2E01Result:
    """Machine-check result for the E2E-01 voice reminder journey."""

    result: str
    checks: list[dict[str, Any]]
    transcript: Optional[str]
    turn_body: Optional[str]
    reminder_id: Optional[str]
    due_at: Optional[str]
    confirm_body: Optional[str]
    hard_approvals: int
    outbound_count: int
    artifacts_dir: str

    @property
    def ok(self) -> bool:
        return self.result == "PASS"


@dataclass
class E2E03Result:
    """Machine-check result for E2E-03 todo WhatsApp → Android journey."""

    result: str
    checks: list[dict[str, Any]]
    todo_id: Optional[str]
    title: Optional[str]
    status: Optional[str]
    artifacts_dir: str

    @property
    def ok(self) -> bool:
        return self.result == "PASS"


@dataclass
class T2ApprovalInboxResult:
    """Machine-check result for T2 Android approval inbox (Accept/Deny alone)."""

    result: str
    checks: list[dict[str, Any]]
    accept_approval_id: Optional[str]
    deny_approval_id: Optional[str]
    calendar_create_after_accept: int
    calendar_create_after_deny: int
    artifacts_dir: str

    @property
    def ok(self) -> bool:
        return self.result == "PASS"


@dataclass
class VirtualUser:
    """Scripted WhatsApp user for harness E2E journeys."""

    owner: str
    timezone: str
    clock: FakeClock
    catcher: OutboundMessageCatcher
    store: ReminderStore
    todo_store: TodoStore
    gateway: ActionGateway
    reminders: ReminderService
    todos: TodoService
    android: AndroidProjectionApi
    android_inbox: AndroidApprovalInboxApi
    transport: MockWhatsAppTransport
    seed_profile: dict[str, Any] = field(default_factory=dict)
    last_turn: Optional[TransportTurnResult] = None
    last_create: Any = None
    last_soft_confirm: Optional[ProposeResult] = None
    last_accept: Optional[AcceptResult] = None
    last_deny: Optional[ApprovalProjection] = None

    @classmethod
    def bootstrap(
        cls,
        *,
        root: Path | None = None,
        owner: str = "+15550001111",
        monday_local: datetime | None = None,
        timezone: str | None = None,
    ) -> "VirtualUser":
        """Seed timezone from memory fixture; fake clock Monday 10:00 local (E2E-01)."""
        repo = root or ROOT
        seed_path = repo / "fixtures" / "memory" / "seed-profile.json"
        seed: dict[str, Any] = {}
        if seed_path.is_file():
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
        tz_name = timezone or (seed.get("identity", {}) or {}).get("timezone") or "Europe/Madrid"
        tz = ZoneInfo(tz_name)
        start = monday_local or datetime(2026, 1, 5, 10, 0, 0, tzinfo=tz)

        clock = FakeClock(start=start)
        catcher = OutboundMessageCatcher()
        store = ReminderStore()
        todo_store = TodoStore()
        gateway = ActionGateway(clock=clock, reminders=store, todos=todo_store)
        reminders = ReminderService(
            store=store,
            clock=clock,
            catcher=catcher,
            gateway=gateway,
            timezone=tz_name,
            recipient=owner,
        )
        todos = TodoService(
            store=todo_store,
            clock=clock,
            catcher=catcher,
            gateway=gateway,
            recipient=owner,
        )
        android = AndroidProjectionApi(
            store=todo_store,
            clock=clock,
            gateway=gateway,
        )
        assert android.approvals is not None
        android_inbox = android.approvals

        vu = cls(
            owner=owner,
            timezone=tz_name,
            clock=clock,
            catcher=catcher,
            store=store,
            todo_store=todo_store,
            gateway=gateway,
            reminders=reminders,
            todos=todos,
            android=android,
            android_inbox=android_inbox,
            transport=MockWhatsAppTransport(  # placeholder; rebound below
                allowlist=[owner],
                catcher=catcher,
            ),
            seed_profile=seed,
        )
        pipeline = TranscriptionPipeline.from_fixtures(
            manifest_path=repo / "fixtures" / "audio" / "manifest.json"
        )
        pipeline.tts.mode = TtsMode.INBOUND
        vu.transport = MockWhatsAppTransport(
            allowlist=[owner],
            catcher=catcher,
            pipeline=pipeline,
            tts_mode=TtsMode.INBOUND,
            agent_handler=vu._agent_handler,
        )
        return vu

    def _agent_handler(
        self,
        transport: MockWhatsAppTransport,
        msg: InboundWhatsAppMessage,
        decision: Any,
    ) -> list[str]:
        """Agent double: reminder/todo utterances → Auto create; else default ack."""
        body = msg.body or ""
        if _looks_like_reminder(body):
            # Fail closed if tier ever drifts off Auto.
            if tier_for("reminder_create") != ApprovalTier.AUTO:
                transport._record_tool("agent.clarify")
                transport._send_outbound(
                    decision.normalized_sender or msg.sender,
                    "Reminder create is not Auto — refusing without approval path.",
                    kind="clarification",
                )
                return ["agent.clarify"]

            transport._record_tool("reminder_create")
            created = self.reminders.create_from_utterance(
                body,
                timezone=self.timezone,
                recipient=self.owner,
            )
            self.last_create = created
            tools = ["reminder_create"]
            if created.ok:
                # ReminderService already wrote confirm via shared catcher;
                # mirror into transport outbound ledger for counter consistency.
                transport.counters.outbound_sends += 1
                if msg.media_type == "audio":
                    spoken = transport.pipeline.maybe_tts_reply(
                        created.confirm_body, inbound_was_audio=True
                    )
                    if spoken:
                        transport.counters.tts_speaks += 1
                        transport.last_tts_spoken = True
                return tools

            transport._record_tool("agent.clarify")
            tools.append("agent.clarify")
            transport._send_outbound(
                decision.normalized_sender or msg.sender,
                f"Could not create reminder: {created.reason}",
                kind="clarification",
            )
            return tools

        if looks_like_todo_add(body):
            if tier_for("todo_add") != ApprovalTier.AUTO:
                transport._record_tool("agent.clarify")
                transport._send_outbound(
                    decision.normalized_sender or msg.sender,
                    "Todo add is not Auto — refusing without approval path.",
                    kind="clarification",
                )
                return ["agent.clarify"]

            transport._record_tool("todo_add")
            created = self.todos.create_from_utterance(
                body,
                recipient=self.owner,
            )
            self.last_create = created
            tools = ["todo_add"]
            if created.ok:
                transport.counters.outbound_sends += 1
                if msg.media_type == "audio":
                    spoken = transport.pipeline.maybe_tts_reply(
                        created.confirm_body, inbound_was_audio=True
                    )
                    if spoken:
                        transport.counters.tts_speaks += 1
                        transport.last_tts_spoken = True
                return tools

            transport._record_tool("agent.clarify")
            tools.append("agent.clarify")
            transport._send_outbound(
                decision.normalized_sender or msg.sender,
                f"Could not create todo: {created.reason}",
                kind="clarification",
            )
            return tools

        return default_agent_handler(transport, msg, decision)

    def inject_text(self, body: str, **kwargs: Any) -> TransportTurnResult:
        self.last_turn = self.transport.inject_text(self.owner, body, **kwargs)
        return self.last_turn

    def inject_audio(self, audio_fixture_id: str, **kwargs: Any) -> TransportTurnResult:
        self.last_turn = self.transport.inject_audio(
            self.owner, audio_fixture_id=audio_fixture_id, **kwargs
        )
        return self.last_turn

    def advance(self, duration: Any) -> datetime:
        return self.clock.advance(duration)

    def reminders_list(self) -> list[Any]:
        return list(self.store.reminders.values())

    def hard_approval_items(self) -> list[Any]:
        return [
            item
            for item in self.gateway.approvals.list()
            if is_hard_action(item.action_type)
            or item.action_type in {"reminder_create", "habit_create"}
        ]

    def pending_approvals(self) -> list[Any]:
        return list(self.gateway.approvals.list(status=ApprovalStatus.PENDING))

    def list_android_approvals(self) -> list[ApprovalProjection]:
        """Pending approvals via the same Android inbox API the product uses."""
        return self.android_inbox.list_pending()

    def accept_approval(self, approval_id: str) -> AcceptResult:
        """Virtual User taps Accept on Android — no human phone required."""
        self.last_accept = self.android_inbox.accept(approval_id)
        return self.last_accept

    def deny_approval(self, approval_id: str) -> ApprovalProjection:
        """Virtual User taps Deny on Android — adapters must not run."""
        self.last_deny = self.android_inbox.deny(approval_id)
        return self.last_deny

    def edit_approval(
        self,
        approval_id: str,
        *,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
        payload_patch: dict[str, Any] | None = None,
        estimated_cost: float | None = None,
    ) -> ApprovalProjection:
        """Virtual User taps Edit on Android — mutate pending details only."""
        return self.android_inbox.edit(
            approval_id,
            summary=summary,
            payload=payload,
            payload_patch=payload_patch,
            estimated_cost=estimated_cost,
        )

    def propose_soft_calendar(
        self,
        *,
        title: str,
        start: str,
        end: str,
        summary: str | None = None,
        source_utterance: str | None = None,
        source_channel: str = "whatsapp",
        **payload_extra: Any,
    ) -> ProposeResult:
        """E2E-04 hook: create pending soft confirm; calendar create_count stays 0.

        Shallow calendar path — full conflict-aware scheduling lands in TASK-13.
        """
        payload: dict[str, Any] = {
            "title": title,
            "start": start,
            "end": end,
            **payload_extra,
        }
        proposed = self.gateway.propose(
            "calendar_create",
            summary or f"Create calendar event: {title}",
            payload,
            source_channel=source_channel,
            source_utterance=source_utterance,
        )
        self.last_soft_confirm = proposed
        return proposed

    def calendar_create_count(self) -> int:
        return self.gateway.calendar.create_count

    def todos_list(self) -> list[Any]:
        return list(self.todo_store.list_all())

    def confirm_messages(self) -> list[Any]:
        return [
            m
            for m in self.catcher.messages
            if m.meta.get("kind") in {"reminder_confirm", "todo_confirm", "todo_dedup"}
        ]

    def snapshot(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "timezone": self.timezone,
            "clock": self.clock.now().isoformat(),
            "reminders": self.store.to_dict(),
            "todos": self.todo_store.to_dict(),
            "android_projection": self.android.snapshot(),
            "android_approvals": self.android_inbox.snapshot(),
            "calendar": {
                "create_count": self.gateway.calendar.create_count,
                "events": list(self.gateway.calendar.events),
            },
            "outbound": self.catcher.to_list(),
            "approvals_pending": [a.id for a in self.pending_approvals()],
            "hard_approvals": [a.id for a in self.hard_approval_items()],
            "transport": self.transport.snapshot(),
        }


def run_e2e_01(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E01Result:
    """E2E-01 — Voice reminder journey (gate-tagged).

    Setup: seed timezone; fake clock Monday 10:00.
    1. Inject audio fixture fx-reminder
    2. STT stub returns expected transcript
    3. Agent creates reminder

    Checks: reminder exists; due = next Sunday 18:00 local;
    outbound confirm captured; no hard approval created.
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-01")
    checks: list[dict[str, Any]] = []

    vu = VirtualUser.bootstrap(root=repo)
    tz = ZoneInfo(vu.timezone)
    expected_due = datetime(2026, 1, 11, 18, 0, 0, tzinfo=tz)

    # Setup assertions
    setup_ok = (
        vu.timezone == "Europe/Madrid"
        and vu.clock.now().weekday() == 0  # Monday
        and vu.clock.now().hour == 10
        and vu.clock.now().minute == 0
    )
    checks.append(
        {
            "id": "e2e-01.setup_timezone_and_clock",
            "result": "PASS" if setup_ok else "FAIL",
            "detail": (
                f"tz={vu.timezone} now={vu.clock.now().isoformat()} "
                f"weekday={vu.clock.now().weekday()}"
            ),
            "gate": True,
        }
    )

    # Step 1–3: inject audio → STT → agent create
    turn = vu.inject_audio(E2E01_AUDIO_FIXTURE)

    stt_ok = (
        turn.allowed
        and turn.transcript == EXPECTED_E2E01_TRANSCRIPT
        and turn.stt_outcome == "ok"
        and (turn.turn_body or "").startswith("[Audio] Remind me Sunday")
        and turn.clarification is None
    )
    checks.append(
        {
            "id": "e2e-01.stt_stub_transcript",
            "result": "PASS" if stt_ok else "FAIL",
            "detail": (
                f"transcript={turn.transcript!r} turn={turn.turn_body!r} "
                f"outcome={turn.stt_outcome} allowed={turn.allowed}"
            ),
            "gate": True,
        }
    )

    agent_ok = "reminder_create" in turn.tool_calls
    checks.append(
        {
            "id": "e2e-01.agent_creates_reminder",
            "result": "PASS" if agent_ok else "FAIL",
            "detail": f"tools={turn.tool_calls} create_ok={getattr(vu.last_create, 'ok', None)}",
            "gate": True,
        }
    )

    reminders = vu.reminders_list()
    rem = reminders[0] if reminders else None
    exists_ok = rem is not None and rem.text.lower() == "call grandma"
    checks.append(
        {
            "id": "e2e-01.reminder_exists",
            "result": "PASS" if exists_ok else "FAIL",
            "detail": (
                f"count={len(reminders)} "
                f"text={rem.text if rem else None!r} id={rem.id if rem else None}"
            ),
            "gate": True,
        }
    )

    due_ok = rem is not None and rem.due_at == expected_due
    checks.append(
        {
            "id": "e2e-01.due_next_sunday_1800_local",
            "result": "PASS" if due_ok else "FAIL",
            "detail": (
                f"due={rem.due_at.isoformat() if rem else None} "
                f"expected={expected_due.isoformat()}"
            ),
            "gate": True,
        }
    )

    confirms = vu.confirm_messages()
    confirm_ok = (
        len(confirms) >= 1
        and "call grandma" in confirms[0].body.lower()
        and confirms[0].meta.get("kind") == "reminder_confirm"
    )
    checks.append(
        {
            "id": "e2e-01.outbound_confirm_captured",
            "result": "PASS" if confirm_ok else "FAIL",
            "detail": (
                f"confirms={len(confirms)} "
                f"body={confirms[0].body if confirms else None!r} "
                f"outbound_total={vu.catcher.count()}"
            ),
            "gate": True,
        }
    )

    hard = vu.hard_approval_items()
    pending = vu.pending_approvals()
    # Auto path: no approval_id on create, no hard items, no pending.
    create = vu.last_create
    no_hard_ok = (
        len(hard) == 0
        and len(pending) == 0
        and create is not None
        and create.ok
        and create.approval_id is None
        and create.tier == "auto"
    )
    checks.append(
        {
            "id": "e2e-01.no_hard_approval",
            "result": "PASS" if no_hard_ok else "FAIL",
            "detail": (
                f"hard={len(hard)} pending={len(pending)} "
                f"approval_id={getattr(create, 'approval_id', None)} "
                f"tier={getattr(create, 'tier', None)}"
            ),
            "gate": True,
        }
    )

    # Sanity: parse of golden transcript agrees with stored due (state not prose).
    parsed = parse_reminder(
        EXPECTED_E2E01_TRANSCRIPT, now=vu.clock.now(), timezone=vu.timezone
    )
    parse_align = rem is not None and rem.due_at == parsed.due_at
    checks.append(
        {
            "id": "e2e-01.parse_aligns_store",
            "result": "PASS" if parse_align else "FAIL",
            "detail": f"parsed_due={parsed.due_at.isoformat()} store_due={rem.due_at.isoformat() if rem else None}",
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E01Result(
        result=overall,
        checks=checks,
        transcript=turn.transcript,
        turn_body=turn.turn_body,
        reminder_id=rem.id if rem else None,
        due_at=rem.due_at.isoformat() if rem else None,
        confirm_body=confirms[0].body if confirms else None,
        hard_approvals=len(hard),
        outbound_count=vu.catcher.count(),
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        vu.catcher.write_json(out / "outbound-messages.json")
        (out / "reminders.json").write_text(
            json.dumps(vu.store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out / "trace.jsonl").write_text(
            json.dumps(
                {
                    "flow": "E2E-01",
                    "setup": {
                        "timezone": vu.timezone,
                        "clock": vu.clock.now().isoformat(),
                        "owner": vu.owner,
                        "audio_fixture": E2E01_AUDIO_FIXTURE,
                    },
                    "turn": {
                        "allowed": turn.allowed,
                        "transcript": turn.transcript,
                        "turn_body": turn.turn_body,
                        "stt_outcome": turn.stt_outcome,
                        "tool_calls": turn.tool_calls,
                        "tts_spoken": turn.tts_spoken,
                    },
                    "create": {
                        "ok": getattr(create, "ok", None),
                        "tier": getattr(create, "tier", None),
                        "approval_id": getattr(create, "approval_id", None),
                        "reason": getattr(create, "reason", None),
                        "reminder_id": rem.id if rem else None,
                        "due_at": rem.due_at.isoformat() if rem else None,
                    },
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="e2e-01",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-01",
                "gate": True,
                "seed_timezone": vu.timezone,
                "audio_fixture": E2E01_AUDIO_FIXTURE,
                "expected_transcript": EXPECTED_E2E01_TRANSCRIPT,
                "expected_due": expected_due.isoformat(),
                "reminder_id": rem.id if rem else None,
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "python3 scripts/run_e2e_01.py",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/e2e-01/",
                },
            },
        )
        stamp = {
            "claim": (
                "E2E-01 voice reminder: Virtual User injects fx-reminder audio; "
                "STT stub returns transcript; agent Auto-creates reminder due next "
                "Sunday 18:00 local; outbound confirm captured; no hard approval"
            ),
            "result": overall,
            "flow": "E2E-01",
            "gate": True,
            "invariants": [
                "INV-INGRESS-003",
            ],
            "checks": [c["id"] for c in checks],
            "commands": [
                "python3 scripts/run_e2e_01.py",
                "./scripts/test-ci.sh",
                "make test-ci",
            ],
            "artifacts": [
                "artifacts/test/e2e-01/report.json",
                "artifacts/test/e2e-01/verification.json",
                "artifacts/test/e2e-01/outbound-messages.json",
                "artifacts/test/e2e-01/reminders.json",
                "artifacts/test/e2e-01/trace.jsonl",
            ],
            "seed_timezone": vu.timezone,
            "expected_due": expected_due.isoformat(),
            "reminder_id": rem.id if rem else None,
            "hard_approvals": len(hard),
        }
        (out / "verification.json").write_text(
            json.dumps(stamp, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return result


def run_e2e_03(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E03Result:
    """E2E-03 — Todo WhatsApp → Android (gate-tagged in test:ci).

    1. Text: 'Add todo: buy oat milk.'
    2. Read Android projection API.

    Checks: same todo id/title/status; completing via Android API reflects in agent store.
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-03")
    checks: list[dict[str, Any]] = []

    vu = VirtualUser.bootstrap(root=repo)
    utterance = EXPECTED_E2E03_UTTERANCE

    # Step 1: inject text → agent creates todo (Auto tier).
    turn = vu.inject_text(utterance)

    inject_ok = (
        turn.allowed
        and "todo_add" in turn.tool_calls
        and getattr(vu.last_create, "ok", False)
        and getattr(vu.last_create, "tier", None) == "auto"
    )
    checks.append(
        {
            "id": "e2e-03.whatsapp_creates_todo",
            "result": "PASS" if inject_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} create_ok={getattr(vu.last_create, 'ok', None)} "
                f"tier={getattr(vu.last_create, 'tier', None)}"
            ),
            "gate": True,
        }
    )

    agent_todo = vu.todos_list()[0] if vu.todos_list() else None
    agent_ok = (
        agent_todo is not None
        and agent_todo.title.lower() == "buy oat milk"
        and agent_todo.status == TodoStatus.OPEN
    )
    checks.append(
        {
            "id": "e2e-03.agent_store_has_todo",
            "result": "PASS" if agent_ok else "FAIL",
            "detail": (
                f"count={len(vu.todos_list())} "
                f"title={agent_todo.title if agent_todo else None!r} "
                f"status={agent_todo.status.value if agent_todo else None}"
            ),
            "gate": True,
        }
    )

    # Step 2: Android projection API reflects same id/title/status.
    projected = vu.android.list_todos()
    proj = projected[0] if projected else None
    projection_ok = (
        proj is not None
        and agent_todo is not None
        and proj.id == agent_todo.id
        and proj.title == agent_todo.title
        and proj.status == agent_todo.status.value
    )
    checks.append(
        {
            "id": "e2e-03.android_projection_equality",
            "result": "PASS" if projection_ok else "FAIL",
            "detail": (
                f"agent_id={agent_todo.id if agent_todo else None} "
                f"android_id={proj.id if proj else None} "
                f"title={proj.title if proj else None!r} status={proj.status if proj else None}"
            ),
            "gate": True,
        }
    )

    get_proj = vu.android.get_todo(agent_todo.id) if agent_todo else None
    get_ok = (
        get_proj is not None
        and agent_todo is not None
        and get_proj.id == agent_todo.id
        and get_proj.title == agent_todo.title
        and get_proj.status == "open"
    )
    checks.append(
        {
            "id": "e2e-03.android_get_matches",
            "result": "PASS" if get_ok else "FAIL",
            "detail": f"get={get_proj.to_dict() if get_proj else None}",
            "gate": True,
        }
    )

    # Step 3: complete via Android API → agent store reflects done.
    completed_proj = vu.android.complete_todo(agent_todo.id) if agent_todo else None
    store_after = vu.todo_store.get(agent_todo.id) if agent_todo else None
    complete_ok = (
        completed_proj is not None
        and store_after is not None
        and completed_proj.status == "done"
        and store_after.status == TodoStatus.DONE
    )
    checks.append(
        {
            "id": "e2e-03.android_complete_reflects_store",
            "result": "PASS" if complete_ok else "FAIL",
            "detail": (
                f"proj_status={completed_proj.status if completed_proj else None} "
                f"store_status={store_after.status.value if store_after else None}"
            ),
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E03Result(
        result=overall,
        checks=checks,
        todo_id=agent_todo.id if agent_todo else None,
        title=agent_todo.title if agent_todo else None,
        status=store_after.status.value if store_after else None,
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        vu.catcher.write_json(out / "outbound-messages.json")
        (out / "todos.json").write_text(
            json.dumps(vu.todo_store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out / "android-projection.json").write_text(
            json.dumps(vu.android.snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="e2e-03",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-03",
                "gate": True,
                "utterance": utterance,
                "todo_id": agent_todo.id if agent_todo else None,
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-03",
                        "python3 scripts/run_e2e_03.py",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/e2e-03/",
                },
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-03 todo sync: WhatsApp text creates todo; Android "
                        "projection API list/get matches id/title/status; "
                        "complete via Android reflects in agent store"
                    ),
                    "result": overall,
                    "flow": "E2E-03",
                    "gate": True,
                    "checks": [c["id"] for c in checks],
                    "commands": [
                        "python3 scripts/run_e2e_03.py",
                        "make e2e-03",
                        "./scripts/test-ci.sh",
                        "make test-ci",
                    ],
                    "artifacts": [
                        "artifacts/test/e2e-03/report.json",
                        "artifacts/test/e2e-03/verification.json",
                        "artifacts/test/e2e-03/todos.json",
                        "artifacts/test/e2e-03/android-projection.json",
                    ],
                    "todo_id": agent_todo.id if agent_todo else None,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return result


def run_t2_approval_inbox(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> T2ApprovalInboxResult:
    """T2 exit — Accept/Deny exercised by Virtual User alone via Android API.

    Soft-confirm calendar path (E2E-04 hooks):
      1. Propose soft calendar → pending; create_count = 0
      2. Virtual User Accept via Android inbox → create_count = 1
      3. Propose another soft calendar → Deny via Android → create stays 1
      4. Edit path: propose → Edit payload → Accept → create once more
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "task-11")
    checks: list[dict[str, Any]] = []

    vu = VirtualUser.bootstrap(root=repo)

    # --- Accept path (soft calendar) ---
    proposed = vu.propose_soft_calendar(
        title="Focus block",
        start="2026-01-09T09:00:00+01:00",
        end="2026-01-09T11:00:00+01:00",
        source_utterance="Schedule focus block Friday 09:00–11:00.",
    )
    pending_before = vu.list_android_approvals()
    create_before_accept = vu.calendar_create_count()
    soft_pending_ok = (
        proposed.ok
        and not proposed.executed
        and proposed.tier == ApprovalTier.SOFT_CONFIRM.value
        and proposed.approval_id is not None
        and create_before_accept == 0
        and len(pending_before) == 1
        and pending_before[0].id == proposed.approval_id
        and pending_before[0].action_type == "calendar_create"
        and pending_before[0].status == ApprovalStatus.PENDING.value
    )
    checks.append(
        {
            "id": "t2.soft_calendar.pending_create_zero",
            "result": "PASS" if soft_pending_ok else "FAIL",
            "detail": (
                f"ok={proposed.ok} executed={proposed.executed} tier={proposed.tier} "
                f"approval_id={proposed.approval_id} create={create_before_accept} "
                f"pending={len(pending_before)}"
            ),
            "gate": True,
        }
    )

    accepted = vu.accept_approval(proposed.approval_id) if proposed.approval_id else None
    create_after_accept = vu.calendar_create_count()
    accept_ok = (
        accepted is not None
        and accepted.ok
        and accepted.approval.status == ApprovalStatus.EXECUTED.value
        and create_after_accept == 1
        and len(vu.list_android_approvals()) == 0
        and len(vu.gateway.calendar.events) == 1
    )
    checks.append(
        {
            "id": "t2.android.accept_executes_once",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accepted, 'ok', None)} "
                f"status={accepted.approval.status if accepted else None} "
                f"create={create_after_accept} events={len(vu.gateway.calendar.events)}"
            ),
            "gate": True,
        }
    )

    # --- Deny path (soft calendar) ---
    denied_prop = vu.propose_soft_calendar(
        title="Dentist",
        start="2026-01-10T15:00:00+01:00",
        end="2026-01-10T16:00:00+01:00",
        source_utterance="Schedule dentist Saturday 15:00.",
    )
    create_before_deny = vu.calendar_create_count()
    denied = vu.deny_approval(denied_prop.approval_id) if denied_prop.approval_id else None
    create_after_deny = vu.calendar_create_count()
    # Attempt execute after deny must fail closed.
    late_exec = (
        vu.gateway.execute(denied_prop.approval_id) if denied_prop.approval_id else None
    )
    deny_ok = (
        denied_prop.ok
        and denied_prop.approval_id is not None
        and create_before_deny == 1  # only prior Accept
        and denied is not None
        and denied.status == ApprovalStatus.DENIED.value
        and create_after_deny == 1
        and late_exec is not None
        and (not late_exec.ok)
        and create_after_deny == vu.calendar_create_count()
        and len(vu.list_android_approvals()) == 0
    )
    checks.append(
        {
            "id": "t2.android.deny_never_executes",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"deny_status={denied.status if denied else None} "
                f"create_before={create_before_deny} create_after={create_after_deny} "
                f"late_exec={getattr(late_exec, 'reason', None)}"
            ),
            "gate": True,
        }
    )

    # --- Edit then Accept ---
    edit_prop = vu.propose_soft_calendar(
        title="Team sync",
        start="2026-01-12T10:00:00+01:00",
        end="2026-01-12T10:30:00+01:00",
    )
    edited = (
        vu.edit_approval(
            edit_prop.approval_id,
            summary="Team sync (edited)",
            payload_patch={"title": "Team sync (edited)", "location": "Room A"},
        )
        if edit_prop.approval_id
        else None
    )
    create_before_edit_accept = vu.calendar_create_count()
    edit_accept = vu.accept_approval(edit_prop.approval_id) if edit_prop.approval_id else None
    create_after_edit_accept = vu.calendar_create_count()
    last_event = vu.gateway.calendar.events[-1] if vu.gateway.calendar.events else {}
    edit_ok = (
        edited is not None
        and edited.summary == "Team sync (edited)"
        and edited.payload.get("title") == "Team sync (edited)"
        and edited.payload.get("location") == "Room A"
        and edited.status == ApprovalStatus.PENDING.value
        and create_before_edit_accept == 1
        and edit_accept is not None
        and edit_accept.ok
        and create_after_edit_accept == 2
        and last_event.get("title") == "Team sync (edited)"
        and last_event.get("location") == "Room A"
    )
    checks.append(
        {
            "id": "t2.android.edit_then_accept",
            "result": "PASS" if edit_ok else "FAIL",
            "detail": (
                f"summary={edited.summary if edited else None!r} "
                f"create={create_after_edit_accept} last_title={last_event.get('title')!r}"
            ),
            "gate": True,
        }
    )

    # --- Hard buy Deny via same Android API (T2 surface covers hard inbox too) ---
    hard = vu.gateway.propose("buy", "Buy protein powder", {"sku": "prot-1", "price": 29.0})
    hard_pending = vu.list_android_approvals()
    hard_deny = vu.deny_approval(hard.approval_id) if hard.approval_id else None
    hard_ok = (
        hard.ok
        and hard.tier == ApprovalTier.HARD_APPROVE.value
        and any(p.id == hard.approval_id for p in hard_pending)
        and hard_deny is not None
        and hard_deny.status == ApprovalStatus.DENIED.value
        and vu.gateway.commerce.buy_count == 0
    )
    checks.append(
        {
            "id": "t2.android.hard_buy_deny",
            "result": "PASS" if hard_ok else "FAIL",
            "detail": (
                f"tier={hard.tier} buy_count={vu.gateway.commerce.buy_count} "
                f"deny={hard_deny.status if hard_deny else None}"
            ),
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = T2ApprovalInboxResult(
        result=overall,
        checks=checks,
        accept_approval_id=proposed.approval_id,
        deny_approval_id=denied_prop.approval_id,
        calendar_create_after_accept=create_after_accept,
        calendar_create_after_deny=create_after_deny,
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        (out / "approvals.json").write_text(
            json.dumps(vu.android_inbox.snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out / "calendar.json").write_text(
            json.dumps(
                {
                    "create_count": vu.calendar_create_count(),
                    "events": vu.gateway.calendar.events,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (out / "trace.jsonl").write_text(
            json.dumps(
                {
                    "flow": "T2-approval-inbox",
                    "accept_id": proposed.approval_id,
                    "deny_id": denied_prop.approval_id,
                    "edit_id": edit_prop.approval_id,
                    "hard_deny_id": hard.approval_id,
                    "calendar_create_count": vu.calendar_create_count(),
                    "buy_count": vu.gateway.commerce.buy_count,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="task-11",
            result=overall,
            checks=checks,
            extra={
                "flow": "T2-Android-approval-inbox",
                "gate": True,
                "t2_exit": overall == "PASS",
                "e2e04_hooks": True,
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-01",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/task-11/",
                },
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "T2 exit: Virtual User alone Accept/Deny/Edit via Android "
                        "approval inbox API; soft-confirm calendar create_count=0 "
                        "until Accept; Deny never executes (E2E-04 hooks)"
                    ),
                    "result": overall,
                    "flow": "T2-Android-approval-inbox",
                    "gate": True,
                    "t2_exit": overall == "PASS",
                    "invariants": ["INV-APPR-003"],
                    "checks": [c["id"] for c in checks],
                    "commands": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make test-ci-fail-closed",
                        "make e2e-01",
                    ],
                    "artifacts": [
                        "artifacts/test/task-11/report.json",
                        "artifacts/test/task-11/verification.json",
                        "artifacts/test/task-11/approvals.json",
                        "artifacts/test/task-11/calendar.json",
                        "artifacts/test/task-11/trace.jsonl",
                    ],
                    "accept_approval_id": proposed.approval_id,
                    "deny_approval_id": denied_prop.approval_id,
                    "calendar_create_after_accept": create_after_accept,
                    "calendar_create_after_deny": create_after_deny,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return result
