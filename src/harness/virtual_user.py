"""Virtual User — scripted client that drives the Gateway like a real user.

Per agent-plan/testing/harnesses-and-fixtures.md:
  inject text/audio → advance fake clock → read state (reminders, approvals, outbound)

No live WhatsApp. Used by gate-tagged E2E flows (E2E-01 first).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from capabilities.bookings.parse import EXPECTED_E2E06_UTTERANCE, looks_like_booking
from capabilities.bookings.service import BookingService, ProposeBookingResult
from capabilities.bookings.store import BookingStatus, BookingStore
from capabilities.calendar.parse import looks_like_schedule
from capabilities.calendar.service import CalendarService, ProposeCalendarResult
from capabilities.calendar.store import CalendarStore
from capabilities.diet.constraints import banned_terms, text_violations
from capabilities.diet.parse import EXPECTED_E2E05_UTTERANCE, looks_like_meal_plan
from capabilities.diet.service import DietService, PlanMealsResult
from capabilities.reminders.parse import parse_reminder
from capabilities.reminders.scheduler import ReminderScheduler
from capabilities.reminders.service import ReminderService
from capabilities.reminders.store import EscalationChannel, ReminderStore
from capabilities.shopping.parse import EXPECTED_E2E07_UTTERANCE, looks_like_shopping
from capabilities.shopping.service import ProposePurchaseResult, ShoppingService
from capabilities.shopping.store import PurchaseStatus, PurchaseStore
from capabilities.todos.parse import looks_like_todo_add
from capabilities.todos.service import TodoService
from capabilities.todos.store import TodoStatus, TodoStore
from channels.android.approvals import AcceptResult, AndroidApprovalInboxApi, ApprovalProjection
from channels.android.notifications import AndroidNotificationCatcher
from channels.android.projection import AndroidProjectionApi
from channels.voice.allowlist import CALL_MODE_FORBIDDEN_TOOLS
from channels.voice.provider import MockVoiceProvider
from harness.artifacts import write_report
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from harness.whatsapp_transport import (
    InboundWhatsAppMessage,
    MockWhatsAppTransport,
    TransportTurnResult,
    default_agent_handler,
)
from intelligence.memory.store import MemoryStore
from intelligence.transcription.pipeline import TranscriptionPipeline
from intelligence.transcription.tts import TtsMode
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import (
    ApprovalError,
    ApprovalStatus,
    ApprovalTier,
    is_hard_action,
    tier_for,
)
from policy.spend_caps import SpendCapConfig

ROOT = Path(__file__).resolve().parents[2]

_REMIND_INTENT = re.compile(
    r"(?:\[Audio\]\s*)?remind\s+me\b",
    re.IGNORECASE,
)

EXPECTED_E2E03_UTTERANCE = "Add todo: buy oat milk."
EXPECTED_E2E04_UTTERANCE = "Schedule focus block Friday 09:00–11:00."
EXPECTED_E2E04_DENY_UTTERANCE = "Schedule dentist Saturday 15:00–16:00."

EXPECTED_E2E01_TRANSCRIPT = "Remind me Sunday at 18:00 to call grandma."
E2E01_AUDIO_FIXTURE = "fx-reminder"

EXPECTED_E2E02_HABIT = "every Sunday at 18:00 remind me to stretch"


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
class E2E02Result:
    """Machine-check result for E2E-02 habit escalation ladder journey."""

    result: str
    checks: list[dict[str, Any]]
    habit_id: Optional[str]
    reminder_id: Optional[str]
    channel_order: list[str]
    call_id: Optional[str]
    summary_queued: bool
    forbidden_blocked: bool
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
class E2E04Result:
    """Machine-check result for E2E-04 calendar soft confirm journey."""

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
class E2E05StructureResult:
    """E2E-05 structure checks (prep for TASK-16 gate; eval lane non-blocking)."""

    result: str
    checks: list[dict[str, Any]]
    plan_date: Optional[str]
    grocery_todo_count: int
    eval_score: Optional[float]
    artifacts_dir: str

    @property
    def ok(self) -> bool:
        return self.result == "PASS"


@dataclass
class E2E05Result:
    """Machine-check result for E2E-05 diet plan → groceries journey."""

    result: str
    checks: list[dict[str, Any]]
    plan_date: Optional[str]
    grocery_todo_count: int
    eval_score: Optional[float]
    artifacts_dir: str

    @property
    def ok(self) -> bool:
        return self.result == "PASS"


@dataclass
class E2E06Result:
    """Machine-check result for E2E-06 Booksy propose → approve → book."""

    result: str
    checks: list[dict[str, Any]]
    accept_approval_id: Optional[str]
    deny_approval_id: Optional[str]
    book_count_after_accept: int
    book_count_after_deny: int
    calendar_create_after_accept: int
    artifacts_dir: str

    @property
    def ok(self) -> bool:
        return self.result == "PASS"


@dataclass
class E2E07Result:
    """Machine-check result for E2E-07 Shopping with cap / freeze (+ deny)."""

    result: str
    checks: list[dict[str, Any]]
    accept_approval_id: Optional[str]
    deny_approval_id: Optional[str]
    freeze_approval_id: Optional[str]
    cap_approval_id: Optional[str]
    buy_count_after_accept: int
    buy_count_after_deny: int
    buy_count_after_freeze: int
    buy_count_after_cap: int
    proposed_price: Optional[float]
    freeze_reason: Optional[str]
    cap_reason: Optional[str]
    artifacts_dir: str

    @property
    def ok(self) -> bool:
        return self.result == "PASS"


@dataclass
class E2E09Result:
    """Machine-check result for E2E-09 ignored hard approval expiry."""

    result: str
    checks: list[dict[str, Any]]
    approval_id: Optional[str]
    status: Optional[str]
    book_count: int
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
    calendar_store: CalendarStore
    gateway: ActionGateway
    reminders: ReminderService
    todos: TodoService
    calendar: CalendarService
    diet: DietService
    bookings: BookingService
    booking_store: BookingStore
    shopping: ShoppingService
    purchase_store: PurchaseStore
    memory: MemoryStore
    android: AndroidProjectionApi
    android_inbox: AndroidApprovalInboxApi
    transport: MockWhatsAppTransport
    seed_profile: dict[str, Any] = field(default_factory=dict)
    last_turn: Optional[TransportTurnResult] = None
    last_create: Any = None
    last_soft_confirm: Optional[ProposeResult] = None
    last_calendar_propose: Optional[ProposeCalendarResult] = None
    last_booking_propose: Optional[ProposeBookingResult] = None
    last_shopping_propose: Optional[ProposePurchaseResult] = None
    last_plan_meals: Optional[PlanMealsResult] = None
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
        calendar_store = CalendarStore()
        gateway = ActionGateway(clock=clock, reminders=store, todos=todo_store)
        gateway.calendar.attach_store(calendar_store)
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
        calendar = CalendarService(
            store=calendar_store,
            clock=clock,
            catcher=catcher,
            gateway=gateway,
            timezone=tz_name,
            recipient=owner,
        )
        mem_root = repo / "artifacts" / "test" / ".vu-memory"
        mem_root.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore.seed_from_fixture(mem_root, seed_path) if seed_path.is_file() else MemoryStore.seed(mem_root)
        diet = DietService(
            calendar=calendar_store,
            todo_store=todo_store,
            clock=clock,
            catcher=catcher,
            memory=memory,
            gateway=gateway,
            timezone=tz_name,
            recipient=owner,
        )
        booking_store = BookingStore()
        bookings = BookingService(
            clock=clock,
            catcher=catcher,
            gateway=gateway,
            calendar_store=calendar_store,
            store=booking_store,
            timezone=tz_name,
            recipient=owner,
            portal_fixture=repo / "fixtures" / "browser" / "booksy-stub-slots.json",
        )
        prefs = (seed.get("preferences") or {}) if isinstance(seed, dict) else {}
        usual = dict(prefs.get("usual_purchases") or {})
        purchase_store = PurchaseStore()
        shopping = ShoppingService(
            clock=clock,
            catcher=catcher,
            gateway=gateway,
            store=purchase_store,
            recipient=owner,
            merchant_fixture=repo / "fixtures" / "shopping" / "merchant-catalog.json",
            caps_config=repo / "config" / "shopping.harness.json",
            usual_from_profile=usual,
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
            calendar_store=calendar_store,
            gateway=gateway,
            reminders=reminders,
            todos=todos,
            calendar=calendar,
            diet=diet,
            bookings=bookings,
            booking_store=booking_store,
            shopping=shopping,
            purchase_store=purchase_store,
            memory=memory,
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

        if looks_like_shopping(body):
            # Hard approve — never buy until Accept (INV-PAY / propose-only).
            if tier_for("buy") != ApprovalTier.HARD_APPROVE:
                transport._record_tool("agent.clarify")
                transport._send_outbound(
                    decision.normalized_sender or msg.sender,
                    "Purchase is not Hard approve — refusing.",
                    kind="clarification",
                )
                return ["agent.clarify"]

            transport._record_tool("buy_propose")
            proposed = self.shopping.propose_from_utterance(
                body,
                recipient=self.owner,
                source_channel="whatsapp",
            )
            self.last_shopping_propose = proposed
            tools = ["buy_propose"]
            if proposed.ok and proposed.approval_id:
                transport.counters.outbound_sends += 1
                if msg.media_type == "audio":
                    spoken = transport.pipeline.maybe_tts_reply(
                        proposed.confirm_body, inbound_was_audio=True
                    )
                    if spoken:
                        transport.counters.tts_speaks += 1
                        transport.last_tts_spoken = True
                return tools

            transport._record_tool("agent.clarify")
            tools.append("agent.clarify")
            transport._send_outbound(
                decision.normalized_sender or msg.sender,
                f"Could not propose purchase: {proposed.reason}",
                kind="clarification",
            )
            return tools

        if looks_like_booking(body):
            # Hard approve — never book until Accept (INV-BOOK-001).
            if tier_for("book") != ApprovalTier.HARD_APPROVE:
                transport._record_tool("agent.clarify")
                transport._send_outbound(
                    decision.normalized_sender or msg.sender,
                    "Booking is not Hard approve — refusing.",
                    kind="clarification",
                )
                return ["agent.clarify"]

            transport._record_tool("book_propose")
            proposed = self.bookings.propose_from_utterance(
                body,
                timezone=self.timezone,
                recipient=self.owner,
                source_channel="whatsapp",
            )
            self.last_booking_propose = proposed
            tools = ["book_propose"]
            if proposed.ok and proposed.approval_id:
                transport.counters.outbound_sends += 1
                if msg.media_type == "audio":
                    spoken = transport.pipeline.maybe_tts_reply(
                        proposed.confirm_body, inbound_was_audio=True
                    )
                    if spoken:
                        transport.counters.tts_speaks += 1
                        transport.last_tts_spoken = True
                return tools

            transport._record_tool("agent.clarify")
            tools.append("agent.clarify")
            transport._send_outbound(
                decision.normalized_sender or msg.sender,
                f"Could not propose booking: {proposed.reason}",
                kind="clarification",
            )
            return tools

        if looks_like_schedule(body):
            # Soft confirm — never write until Accept (INV-APPR-003).
            if tier_for("calendar_create") != ApprovalTier.SOFT_CONFIRM:
                transport._record_tool("agent.clarify")
                transport._send_outbound(
                    decision.normalized_sender or msg.sender,
                    "Calendar create is not Soft confirm — refusing.",
                    kind="clarification",
                )
                return ["agent.clarify"]

            transport._record_tool("calendar_propose")
            proposed = self.calendar.propose_from_utterance(
                body,
                timezone=self.timezone,
                recipient=self.owner,
                source_channel="whatsapp",
            )
            self.last_calendar_propose = proposed
            self.last_soft_confirm = proposed.gateway_result
            tools = ["calendar_propose"]
            if proposed.ok and proposed.approval_id:
                transport.counters.outbound_sends += 1
                if msg.media_type == "audio":
                    spoken = transport.pipeline.maybe_tts_reply(
                        proposed.confirm_body, inbound_was_audio=True
                    )
                    if spoken:
                        transport.counters.tts_speaks += 1
                        transport.last_tts_spoken = True
                return tools

            transport._record_tool("agent.clarify")
            tools.append("agent.clarify")
            transport._send_outbound(
                decision.normalized_sender or msg.sender,
                f"Could not propose calendar event: {proposed.reason}",
                kind="clarification",
            )
            return tools

        if looks_like_meal_plan(body):
            if tier_for("diet_draft") != ApprovalTier.AUTO:
                transport._record_tool("agent.clarify")
                transport._send_outbound(
                    decision.normalized_sender or msg.sender,
                    "Diet draft is not Auto — refusing.",
                    kind="clarification",
                )
                return ["agent.clarify"]

            transport._record_tool("diet_draft")
            planned = self.diet.plan_from_utterance(
                body,
                recipient=self.owner,
                timezone=self.timezone,
            )
            self.last_plan_meals = planned
            tools = ["diet_draft"]
            if planned.ok:
                transport.counters.outbound_sends += 1
                if msg.media_type == "audio":
                    spoken = transport.pipeline.maybe_tts_reply(
                        planned.confirm_body, inbound_was_audio=True
                    )
                    if spoken:
                        transport.counters.tts_speaks += 1
                        transport.last_tts_spoken = True
                tools.append("todo_add")
                return tools

            transport._record_tool("agent.clarify")
            tools.append("agent.clarify")
            transport._send_outbound(
                decision.normalized_sender or msg.sender,
                f"Could not plan meals: {planned.reason}",
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
        self.bookings.mark_denied_for_approval(approval_id)
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
        """E2E-04 hook: create pending soft confirm; calendar create_count stays 0."""
        result = self.calendar.propose_event(
            title=title,
            start=start,
            end=end,
            summary=summary,
            source_utterance=source_utterance,
            source_channel=source_channel,
            **payload_extra,
        )
        self.last_calendar_propose = result
        proposed = result.gateway_result
        if proposed is None:
            # Fail closed — still return a ProposeResult-shaped object via gateway.
            proposed = self.gateway.propose(
                "calendar_create",
                summary or f"Create calendar event: {title}",
                {"title": title, "start": start, "end": end, **payload_extra},
                source_channel=source_channel,
                source_utterance=source_utterance,
            )
        self.last_soft_confirm = proposed
        return proposed

    def schedule_from_utterance(self, utterance: str) -> ProposeCalendarResult:
        """NL path for E2E-04: Schedule … → pending soft confirm (create_count=0)."""
        result = self.calendar.propose_from_utterance(
            utterance,
            timezone=self.timezone,
            recipient=self.owner,
            source_channel="whatsapp",
        )
        self.last_calendar_propose = result
        self.last_soft_confirm = result.gateway_result
        return result

    def calendar_create_count(self) -> int:
        return self.gateway.calendar.create_count

    def book_count(self) -> int:
        return self.gateway.commerce.book_count

    def book_from_utterance(self, utterance: str) -> ProposeBookingResult:
        """NL path for E2E-06: Book … → pending hard approve (book_count=0)."""
        result = self.bookings.propose_from_utterance(
            utterance,
            timezone=self.timezone,
            recipient=self.owner,
            source_channel="whatsapp",
        )
        self.last_booking_propose = result
        return result

    def buy_count(self) -> int:
        return self.gateway.commerce.buy_count

    def buy_from_utterance(self, utterance: str) -> ProposePurchaseResult:
        """NL path for E2E-07: Buy … → pending hard approve (buy_count=0)."""
        result = self.shopping.propose_from_utterance(
            utterance,
            recipient=self.owner,
            source_channel="whatsapp",
        )
        self.last_shopping_propose = result
        return result

    def todos_list(self) -> list[Any]:
        return list(self.todo_store.list_all())

    def confirm_messages(self) -> list[Any]:
        return [
            m
            for m in self.catcher.messages
            if m.meta.get("kind")
            in {
                "reminder_confirm",
                "todo_confirm",
                "todo_dedup",
                "calendar_propose",
                "diet_plan",
                "booking_propose",
                "booking_confirm",
                "shopping_propose",
                "shopping_receipt",
            }
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
                "store": self.calendar_store.to_dict(),
            },
            "bookings": {
                "book_count": self.gateway.commerce.book_count,
                "book_attempt_count": self.gateway.commerce.book_attempt_count,
                "tasks": self.booking_store.to_dict(),
            },
            "shopping": {
                "buy_count": self.gateway.commerce.buy_count,
                "buy_attempt_count": self.gateway.commerce.buy_attempt_count,
                "tasks": self.purchase_store.to_dict(),
                "spend": self.gateway.spend.snapshot(),
                "rejections": list(self.gateway.execute_rejections),
            },
            "outbound": self.catcher.to_list(),
            "approvals_pending": [a.id for a in self.pending_approvals()],
            "hard_approvals": [a.id for a in self.hard_approval_items()],
            "transport": self.transport.snapshot(),
            "memory_constraints": self.memory.planning_constraints(),
            "last_meal_plan": (
                self.last_plan_meals.plan.to_dict()
                if self.last_plan_meals and self.last_plan_meals.plan
                else None
            ),
            "last_booking": (
                {
                    "approval_id": self.last_booking_propose.approval_id,
                    "task_id": self.last_booking_propose.task_id,
                    "options": len(self.last_booking_propose.options),
                    "reason": self.last_booking_propose.reason,
                }
                if self.last_booking_propose
                else None
            ),
            "last_shopping": (
                {
                    "approval_id": self.last_shopping_propose.approval_id,
                    "task_id": self.last_shopping_propose.task_id,
                    "price": self.last_shopping_propose.price,
                    "sku": self.last_shopping_propose.sku,
                    "reason": self.last_shopping_propose.reason,
                }
                if self.last_shopping_propose
                else None
            ),
        }

    def grocery_todos(self) -> list[Any]:
        return [
            t
            for t in self.todo_store.list_open()
            if "grocery" in t.tags or t.title.lower().startswith("buy ")
        ]


def run_e2e_05_structure(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E05StructureResult:
    """E2E-05 structure checks — diet plan → groceries (non-gate prep for TASK-16).

    1. Seed memory with dislikes/allergies (fixture profile).
    2. 'Plan meals for tomorrow.'
    3. Structured plan + grocery todos; banned ingredients absent.
    4. Optional eval lane score recorded (non-blocking).
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-05-structure")
    checks: list[dict[str, Any]] = []

    vu = VirtualUser.bootstrap(root=repo)
    constraints = vu.memory.planning_constraints()
    seed_ok = (
        "peanuts" in constraints.get("allergies", [])
        and "shellfish" in constraints.get("food_dislikes", [])
        and constraints.get("diet_phase") == "low carb"
    )
    checks.append(
        {
            "id": "e2e-05.structure.memory_seeded",
            "result": "PASS" if seed_ok else "FAIL",
            "detail": str(constraints),
            "gate": False,
        }
    )

    turn = vu.inject_text(EXPECTED_E2E05_UTTERANCE)
    planned = vu.last_plan_meals
    agent_ok = (
        turn.allowed
        and "diet_draft" in turn.tool_calls
        and planned is not None
        and planned.ok
        and planned.plan is not None
    )
    checks.append(
        {
            "id": "e2e-05.structure.agent_plans",
            "result": "PASS" if agent_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} ok={getattr(planned, 'ok', None)} "
                f"reason={getattr(planned, 'reason', None)}"
            ),
            "gate": False,
        }
    )

    plan = planned.plan if planned else None
    structured_ok = bool(
        plan
        and len(plan.meals) >= 3
        and plan.grocery_items
        and all(m.slot and m.name and m.ingredients for m in plan.meals)
    )
    checks.append(
        {
            "id": "e2e-05.structure.structured_plan",
            "result": "PASS" if structured_ok else "FAIL",
            "detail": (
                f"meals={len(plan.meals) if plan else 0} "
                f"grocery={len(plan.grocery_items) if plan else 0}"
            ),
            "gate": False,
        }
    )

    banned = banned_terms(constraints)
    violations: list[str] = []
    if plan:
        for meal in plan.meals:
            blob = " ".join([meal.name, *meal.ingredients])
            violations.extend(text_violations(blob, banned))
        for item in plan.grocery_items:
            violations.extend(text_violations(item, banned))
    absent_ok = len(violations) == 0
    checks.append(
        {
            "id": "e2e-05.structure.banned_absent",
            "result": "PASS" if absent_ok else "FAIL",
            "detail": f"violations={violations}",
            "gate": False,
        }
    )

    grocery = vu.grocery_todos()
    grocery_ok = len(grocery) >= len(plan.grocery_items) if plan else False
    checks.append(
        {
            "id": "e2e-05.structure.grocery_todos",
            "result": "PASS" if grocery_ok else "FAIL",
            "detail": f"grocery_todos={len(grocery)} items={len(plan.grocery_items) if plan else 0}",
            "gate": False,
        }
    )

    eval_score = planned.eval_result.score if planned and planned.eval_result else None
    eval_ok = eval_score is not None and eval_score >= 0.6
    checks.append(
        {
            "id": "e2e-05.structure.eval_lane_optional",
            "result": "PASS" if eval_ok else "FAIL",
            "detail": f"score={eval_score} blocking=false",
            "gate": False,
            "blocking": False,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E05StructureResult(
        result=overall,
        checks=checks,
        plan_date=plan.plan_date.isoformat() if plan else None,
        grocery_todo_count=len(grocery),
        eval_score=eval_score,
        artifacts_dir=str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        write_report(
            out,
            layer="e2e-05-structure",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-05",
                "gate": False,
                "eval_lane_blocking": False,
                "harness": "VirtualUser",
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-05 structure: memory constraints → plan meals for tomorrow "
                        "→ structured plan + grocery todos; banned ingredients absent"
                    ),
                    "result": overall,
                    "flow": "E2E-05",
                    "gate": False,
                    "e2e05_ready": overall == "PASS",
                    "eval_lane_blocking": False,
                    "eval_score": eval_score,
                    "checks": [c["id"] for c in checks],
                    "commands": ["./scripts/test-ci.sh", "make test-ci"],
                    "artifacts": [
                        "artifacts/test/e2e-05-structure/report.json",
                        "artifacts/test/e2e-05-structure/verification.json",
                        "artifacts/test/e2e-05-structure/meal-plan.json",
                        "artifacts/test/e2e-05-structure/grocery-todos.json",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if plan:
            (out / "meal-plan.json").write_text(
                json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        (out / "grocery-todos.json").write_text(
            json.dumps(vu.todo_store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        vu.catcher.write_json(out / "outbound-messages.json")

    return result


def run_e2e_05(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E05Result:
    """E2E-05 — Diet plan → groceries (gate-tagged).

    1. Seed memory with dislikes/allergies (fixture profile).
    2. 'Plan meals for tomorrow.'
    3. Structured plan + grocery todos; banned ingredients absent.
    4. Optional eval lane score recorded (non-blocking).
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-05")
    checks: list[dict[str, Any]] = []

    vu = VirtualUser.bootstrap(root=repo)
    constraints = vu.memory.planning_constraints()
    seed_ok = (
        "peanuts" in constraints.get("allergies", [])
        and "shellfish" in constraints.get("food_dislikes", [])
        and constraints.get("diet_phase") == "low carb"
    )
    checks.append(
        {
            "id": "e2e-05.memory_seeded",
            "result": "PASS" if seed_ok else "FAIL",
            "detail": str(constraints),
            "gate": True,
        }
    )

    turn = vu.inject_text(EXPECTED_E2E05_UTTERANCE)
    planned = vu.last_plan_meals
    agent_ok = (
        turn.allowed
        and "diet_draft" in turn.tool_calls
        and planned is not None
        and planned.ok
        and planned.plan is not None
    )
    checks.append(
        {
            "id": "e2e-05.agent_plans",
            "result": "PASS" if agent_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} ok={getattr(planned, 'ok', None)} "
                f"reason={getattr(planned, 'reason', None)}"
            ),
            "gate": True,
        }
    )

    plan = planned.plan if planned else None
    structured_ok = bool(
        plan
        and len(plan.meals) >= 3
        and plan.grocery_items
        and all(m.slot and m.name and m.ingredients for m in plan.meals)
    )
    checks.append(
        {
            "id": "e2e-05.structured_plan",
            "result": "PASS" if structured_ok else "FAIL",
            "detail": (
                f"meals={len(plan.meals) if plan else 0} "
                f"grocery={len(plan.grocery_items) if plan else 0}"
            ),
            "gate": True,
        }
    )

    banned = banned_terms(constraints)
    violations: list[str] = []
    if plan:
        for meal in plan.meals:
            blob = " ".join([meal.name, *meal.ingredients])
            violations.extend(text_violations(blob, banned))
        for item in plan.grocery_items:
            violations.extend(text_violations(item, banned))
    absent_ok = len(violations) == 0
    checks.append(
        {
            "id": "e2e-05.banned_absent",
            "result": "PASS" if absent_ok else "FAIL",
            "detail": f"violations={violations}",
            "gate": True,
        }
    )

    grocery = vu.grocery_todos()
    grocery_ok = len(grocery) >= len(plan.grocery_items) if plan else False
    checks.append(
        {
            "id": "e2e-05.grocery_todos",
            "result": "PASS" if grocery_ok else "FAIL",
            "detail": f"grocery_todos={len(grocery)} items={len(plan.grocery_items) if plan else 0}",
            "gate": True,
        }
    )

    eval_score = planned.eval_result.score if planned and planned.eval_result else None
    eval_ok = eval_score is not None and eval_score >= 0.6
    checks.append(
        {
            "id": "e2e-05.eval_lane_optional",
            "result": "PASS" if eval_ok else "FAIL",
            "detail": f"score={eval_score} blocking=false",
            "gate": False,
            "blocking": False,
        }
    )

    gate_checks = [c for c in checks if c.get("gate", True) and c.get("blocking", True) is not False]
    overall = "PASS" if all(c["result"] == "PASS" for c in gate_checks) else "FAIL"
    result = E2E05Result(
        result=overall,
        checks=checks,
        plan_date=plan.plan_date.isoformat() if plan else None,
        grocery_todo_count=len(grocery),
        eval_score=eval_score,
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        write_report(
            out,
            layer="e2e-05",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-05",
                "gate": True,
                "eval_lane_blocking": False,
                "utterance": EXPECTED_E2E05_UTTERANCE,
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-05",
                        "python3 scripts/run_e2e_05.py",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/e2e-05/",
                },
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-05 diet → groceries: seed memory with dislikes/allergies → "
                        "'Plan meals for tomorrow.' → structured plan + grocery todos; "
                        "banned ingredients absent"
                    ),
                    "result": overall,
                    "flow": "E2E-05",
                    "gate": True,
                    "t3_exit": overall == "PASS",
                    "eval_lane_blocking": False,
                    "eval_score": eval_score,
                    "checks": [c["id"] for c in checks],
                    "commands": [
                        "python3 scripts/run_e2e_05.py",
                        "make e2e-05",
                        "./scripts/test-ci.sh",
                        "make test-ci",
                    ],
                    "artifacts": [
                        "artifacts/test/e2e-05/report.json",
                        "artifacts/test/e2e-05/verification.json",
                        "artifacts/test/e2e-05/meal-plan.json",
                        "artifacts/test/e2e-05/grocery-todos.json",
                        "artifacts/test/e2e-05/outbound-messages.json",
                    ],
                    "grocery_todo_count": len(grocery),
                    "plan_date": plan.plan_date.isoformat() if plan else None,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if plan:
            (out / "meal-plan.json").write_text(
                json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        (out / "grocery-todos.json").write_text(
            json.dumps(vu.todo_store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        vu.catcher.write_json(out / "outbound-messages.json")

    return result


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


def run_e2e_02(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E02Result:
    """E2E-02 — Habit escalation ladder (gate-tagged; T4 exit).

    Setup: recurring high-priority habit; quiet hours off.
    1. Advance clock to fire → WhatsApp reminder.
    2. Advance without completion → Android notification.
    3. Advance again → mock outbound call.
    4. After-call summary queued to WhatsApp.

    Checks: ordered channel touches; call tools exclude buy/book/self-mod-apply.
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-02")
    checks: list[dict[str, Any]] = []

    vu = VirtualUser.bootstrap(root=repo)

    # Setup: quiet hours off (seed profile has quiet hours by default).
    vu.memory.remember(
        "preferences",
        "quiet_hours",
        {"enabled": False},
        explicit=True,
    )
    prefs = vu.memory.load_hot_profile().get("preferences", {})
    quiet = prefs.get("quiet_hours") or {}
    quiet_off = quiet.get("enabled") is False or quiet == {}
    checks.append(
        {
            "id": "e2e-02.setup_quiet_hours_off",
            "result": "PASS" if quiet_off else "FAIL",
            "detail": f"quiet_hours={quiet}",
            "gate": True,
        }
    )

    created = vu.reminders.create_from_utterance(
        EXPECTED_E2E02_HABIT,
        as_habit=True,
        habit_priority="high",
        escalation_enabled=True,
    )
    habit = created.habit
    rem = created.reminder
    setup_ok = (
        created.ok
        and habit is not None
        and rem is not None
        and habit.priority == "high"
        and habit.escalation_enabled
        and habit.escalation_step == 0
        and habit.current_channel() is EscalationChannel.WHATSAPP
        and rem.kind.value == "recurring"
    )
    checks.append(
        {
            "id": "e2e-02.setup_high_priority_habit",
            "result": "PASS" if setup_ok else "FAIL",
            "detail": (
                f"ok={created.ok} habit={getattr(habit, 'id', None)} "
                f"priority={getattr(habit, 'priority', None)} "
                f"escalation={getattr(habit, 'escalation_enabled', None)} "
                f"step={getattr(habit, 'escalation_step', None)}"
            ),
            "gate": True,
        }
    )

    voice = MockVoiceProvider(vu.catcher, vu.clock, default_to=vu.owner)
    android = AndroidNotificationCatcher(vu.clock, vu.catcher, default_to=vu.owner)
    # auto_complete_call=False so step 3 places a live call; step 4 ends + summary.
    sched = ReminderScheduler(
        vu.store,
        vu.clock,
        vu.catcher,
        kill=vu.gateway.kill,
        default_recipient=vu.owner,
        voice=voice,
        android=android,
        auto_complete_call=False,
    )

    # Step 1 — Advance to fire → WhatsApp reminder.
    assert rem is not None and habit is not None
    fires1 = sched.advance(rem.due_at - vu.clock.now())
    habit1 = vu.store.get_habit(habit.id)
    wa_msgs = [
        m
        for m in vu.catcher.messages
        if m.channel == "whatsapp" and m.meta.get("kind") == "reminder_fire"
    ]
    step1_ok = (
        len(fires1) == 1
        and fires1[0].emitted
        and fires1[0].channel == "whatsapp"
        and len(wa_msgs) >= 1
        and any("Habit reminder:" in m.body for m in wa_msgs)
        and android.count() == 0
        and voice.call_count == 0
        and habit1 is not None
        and habit1.escalation_step == 1
        and habit1.current_channel() is EscalationChannel.ANDROID
        and not habit1.completed_this_cycle
    )
    checks.append(
        {
            "id": "e2e-02.step1_whatsapp_reminder",
            "result": "PASS" if step1_ok else "FAIL",
            "detail": (
                f"channel={fires1[0].channel if fires1 else None} "
                f"wa_fires={len(wa_msgs)} android={android.count()} "
                f"calls={voice.call_count} step={getattr(habit1, 'escalation_step', None)}"
            ),
            "gate": True,
        }
    )

    # Step 2 — Advance without completion → Android notification.
    rem_after_1 = vu.store.get(rem.id)
    assert rem_after_1 is not None
    fires2 = sched.advance(rem_after_1.due_at - vu.clock.now())
    habit2 = vu.store.get_habit(habit.id)
    step2_ok = (
        len(fires2) == 1
        and fires2[0].emitted
        and fires2[0].channel == "android"
        and fires2[0].notification_id is not None
        and android.count() == 1
        and any(m.channel == "android" for m in vu.catcher.messages)
        and voice.call_count == 0
        and habit2 is not None
        and habit2.escalation_step == 2
        and habit2.current_channel() is EscalationChannel.CALL
        and not habit2.completed_this_cycle
    )
    checks.append(
        {
            "id": "e2e-02.step2_android_notification",
            "result": "PASS" if step2_ok else "FAIL",
            "detail": (
                f"channel={fires2[0].channel if fires2 else None} "
                f"notification_id={fires2[0].notification_id if fires2 else None} "
                f"android={android.count()} step={getattr(habit2, 'escalation_step', None)}"
            ),
            "gate": True,
        }
    )

    # Step 3 — Advance again → mock outbound call (still active; no summary yet).
    rem_after_2 = vu.store.get(rem.id)
    assert rem_after_2 is not None
    fires3 = sched.advance(rem_after_2.due_at - vu.clock.now())
    call_id = fires3[0].call_id if fires3 else None
    session = voice.get(call_id) if call_id else None
    step3_ok = (
        len(fires3) == 1
        and fires3[0].emitted
        and fires3[0].channel == "call"
        and call_id is not None
        and session is not None
        and session.status == "active"
        and voice.call_count == 1
        and not fires3[0].summary_queued
    )
    checks.append(
        {
            "id": "e2e-02.step3_outbound_call",
            "result": "PASS" if step3_ok else "FAIL",
            "detail": (
                f"channel={fires3[0].channel if fires3 else None} "
                f"call_id={call_id} status={getattr(session, 'status', None)} "
                f"call_count={voice.call_count}"
            ),
            "gate": True,
        }
    )

    # Call tools exclude buy/book/self-mod-apply (INV-APPR-005 on live escalation call).
    blocked: list[bool] = []
    block_reasons: list[str] = []
    if call_id is not None and session is not None and session.status == "active":
        for tool in sorted(CALL_MODE_FORBIDDEN_TOOLS):
            res = voice.invoke_tool(call_id, tool, {"item": tool})
            ok_block = (not res.ok) and res.reason == "call_mode_forbidden_hard_action"
            blocked.append(ok_block)
            block_reasons.append(f"{tool}:{res.reason}")
        read_ok = voice.invoke_tool(call_id, "memory_read", {"key": "prefs"}).ok
    else:
        read_ok = False
    forbidden_ok = len(blocked) == len(CALL_MODE_FORBIDDEN_TOOLS) and all(blocked) and read_ok
    checks.append(
        {
            "id": "e2e-02.call_tools_exclude_hard_actions",
            "result": "PASS" if forbidden_ok else "FAIL",
            "detail": f"blocked={block_reasons} read_ok={read_ok}",
            "gate": True,
        }
    )

    # Step 4 — After-call summary queued to WhatsApp.
    summary_queued = False
    if call_id is not None:
        ended = voice.end_call(call_id, outcome="reminder_delivered")
        summary_queued = ended.summary_queued
    summaries = [
        m
        for m in vu.catcher.messages
        if m.channel == "whatsapp" and m.meta.get("kind") == "after_call_summary"
    ]
    step4_ok = (
        summary_queued
        and len(summaries) == 1
        and "Call summary:" in summaries[0].body
        and summaries[0].meta.get("call_id") == call_id
    )
    checks.append(
        {
            "id": "e2e-02.step4_after_call_whatsapp_summary",
            "result": "PASS" if step4_ok else "FAIL",
            "detail": (
                f"summary_queued={summary_queued} summaries={len(summaries)} "
                f"body={summaries[0].body if summaries else None!r}"
            ),
            "gate": True,
        }
    )

    # Ordered channel touches: WhatsApp → Android → call.
    touch_order = [f.channel for f in (fires1 + fires2 + fires3) if f.emitted]
    order_ok = touch_order == ["whatsapp", "android", "call"]
    ladder_touches = sched.ladder.channel_touch_order() if sched.ladder else []
    ladder_ok = ladder_touches == ["whatsapp", "android", "call"]
    checks.append(
        {
            "id": "e2e-02.ordered_channel_touches",
            "result": "PASS" if order_ok and ladder_ok else "FAIL",
            "detail": f"fires={touch_order} ladder={ladder_touches}",
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E02Result(
        result=overall,
        checks=checks,
        habit_id=habit.id if habit else None,
        reminder_id=rem.id if rem else None,
        channel_order=touch_order,
        call_id=call_id,
        summary_queued=summary_queued,
        forbidden_blocked=forbidden_ok,
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        vu.catcher.write_json(out / "outbound-messages.json")
        android_path = out / "android-notifications.json"
        android_path.write_text(
            json.dumps(android.to_list(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out / "calls.json").write_text(
            json.dumps(voice.snapshot(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out / "reminders.json").write_text(
            json.dumps(vu.store.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out / "escalation-touches.json").write_text(
            json.dumps(
                {
                    "channel_order": touch_order,
                    "ladder_touches": ladder_touches,
                    "fires": [
                        {
                            "channel": f.channel,
                            "emitted": f.emitted,
                            "escalation_step": f.escalation_step,
                            "call_id": f.call_id,
                            "notification_id": f.notification_id,
                            "summary_queued": f.summary_queued,
                        }
                        for f in (fires1 + fires2 + fires3)
                    ],
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
                    "flow": "E2E-02",
                    "setup": {
                        "timezone": vu.timezone,
                        "clock_start": "2026-01-05T10:00:00+01:00",
                        "quiet_hours": quiet,
                        "habit_utterance": EXPECTED_E2E02_HABIT,
                        "habit_priority": "high",
                        "escalation_enabled": True,
                    },
                    "habit_id": habit.id if habit else None,
                    "reminder_id": rem.id if rem else None,
                    "channel_order": touch_order,
                    "call_id": call_id,
                    "summary_queued": summary_queued,
                    "forbidden_blocked": forbidden_ok,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="e2e-02",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-02",
                "gate": True,
                "t4_exit": True,
                "habit_id": habit.id if habit else None,
                "reminder_id": rem.id if rem else None,
                "channel_order": touch_order,
                "call_id": call_id,
                "invariants": ["INV-APPR-005"],
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "python3 scripts/run_e2e_02.py",
                        "make e2e-02",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "prior_gates": [
                        "make e2e-01",
                        "make e2e-03",
                        "make e2e-04",
                        "make e2e-05",
                    ],
                    "artifacts": "artifacts/test/e2e-02/",
                },
            },
        )
        stamp = {
            "claim": (
                "E2E-02 habit escalation ladder: high-priority recurring habit with "
                "quiet hours off climbs WhatsApp → Android → outbound call without "
                "completion; after-call WhatsApp summary queued; mid-call tools "
                "exclude buy/book/self_mod_apply (INV-APPR-005). T4 exit."
            ),
            "result": overall,
            "flow": "E2E-02",
            "gate": True,
            "t4_exit": True,
            "invariants": ["INV-APPR-005"],
            "checks": [c["id"] for c in checks],
            "channel_order": touch_order,
            "commands": [
                "python3 scripts/run_e2e_02.py",
                "make e2e-02",
                "./scripts/test-ci.sh",
                "make test-ci",
            ],
            "artifacts": [
                "artifacts/test/e2e-02/report.json",
                "artifacts/test/e2e-02/verification.json",
                "artifacts/test/e2e-02/outbound-messages.json",
                "artifacts/test/e2e-02/android-notifications.json",
                "artifacts/test/e2e-02/calls.json",
                "artifacts/test/e2e-02/escalation-touches.json",
                "artifacts/test/e2e-02/reminders.json",
                "artifacts/test/e2e-02/trace.jsonl",
            ],
            "habit_id": habit.id if habit else None,
            "reminder_id": rem.id if rem else None,
            "call_id": call_id,
            "summary_queued": summary_queued,
            "forbidden_blocked": forbidden_ok,
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


def run_e2e_04(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E04Result:
    """E2E-04 — Calendar soft confirm (gate-tagged).

    Accept path:
      1. Text: 'Schedule focus block Friday 09:00–11:00.'
      2. Pending soft confirm; calendar adapter create_count = 0.
      3. Accept → event created once.

    Deny path (isolated Virtual User):
      Propose another event → Deny → create_count stays 0; late execute blocked.
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-04")
    checks: list[dict[str, Any]] = []
    utterance = EXPECTED_E2E04_UTTERANCE
    deny_utterance = EXPECTED_E2E04_DENY_UTTERANCE

    # --- Accept path ---
    vu = VirtualUser.bootstrap(root=repo)
    turn = vu.inject_text(utterance)
    proposed = vu.last_soft_confirm
    calendar_propose = vu.last_calendar_propose

    propose_ok = (
        turn.allowed
        and "calendar_propose" in turn.tool_calls
        and proposed is not None
        and proposed.ok
        and not proposed.executed
        and proposed.tier == ApprovalTier.SOFT_CONFIRM.value
        and proposed.approval_id is not None
        and vu.calendar_create_count() == 0
        and calendar_propose is not None
        and calendar_propose.parsed is not None
        and calendar_propose.parsed.start.isoformat() == "2026-01-09T09:00:00+01:00"
        and calendar_propose.parsed.end.isoformat() == "2026-01-09T11:00:00+01:00"
    )
    checks.append(
        {
            "id": "e2e-04.whatsapp_proposes_soft_confirm",
            "result": "PASS" if propose_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} ok={getattr(proposed, 'ok', None)} "
                f"tier={getattr(proposed, 'tier', None)} create={vu.calendar_create_count()} "
                f"start={calendar_propose.parsed.start.isoformat() if calendar_propose and calendar_propose.parsed else None}"
            ),
            "gate": True,
        }
    )

    pending = vu.list_android_approvals()
    pending_ok = (
        len(pending) == 1
        and proposed is not None
        and proposed.approval_id is not None
        and pending[0].id == proposed.approval_id
        and pending[0].action_type == "calendar_create"
        and pending[0].status == ApprovalStatus.PENDING.value
        and vu.calendar_create_count() == 0
        and len(vu.gateway.calendar.events) == 0
    )
    checks.append(
        {
            "id": "e2e-04.pending_soft_confirm_create_zero",
            "result": "PASS" if pending_ok else "FAIL",
            "detail": (
                f"pending={len(pending)} create={vu.calendar_create_count()} "
                f"events={len(vu.gateway.calendar.events)}"
            ),
            "gate": True,
        }
    )

    accepted = vu.accept_approval(proposed.approval_id) if proposed and proposed.approval_id else None
    create_after_accept = vu.calendar_create_count()
    events_after_accept = list(vu.gateway.calendar.events)
    last_event = events_after_accept[0] if events_after_accept else {}
    accept_ok = (
        accepted is not None
        and accepted.ok
        and accepted.approval.status == ApprovalStatus.EXECUTED.value
        and create_after_accept == 1
        and len(events_after_accept) == 1
        and last_event.get("title", "").lower() == "focus block"
        and last_event.get("start") == "2026-01-09T09:00:00+01:00"
        and len(vu.list_android_approvals()) == 0
    )
    checks.append(
        {
            "id": "e2e-04.accept_creates_once",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accepted, 'ok', None)} create={create_after_accept} "
                f"events={len(events_after_accept)} title={last_event.get('title')!r}"
            ),
            "gate": True,
        }
    )

    # --- Deny path (fresh Virtual User — no prior calendar writes) ---
    vu_deny = VirtualUser.bootstrap(root=repo)
    deny_turn = vu_deny.inject_text(deny_utterance)
    denied_prop = vu_deny.last_soft_confirm
    create_before_deny = vu_deny.calendar_create_count()
    denied = (
        vu_deny.deny_approval(denied_prop.approval_id)
        if denied_prop and denied_prop.approval_id
        else None
    )
    create_after_deny = vu_deny.calendar_create_count()
    late_exec = (
        vu_deny.gateway.execute(denied_prop.approval_id)
        if denied_prop and denied_prop.approval_id
        else None
    )
    deny_ok = (
        deny_turn.allowed
        and "calendar_propose" in deny_turn.tool_calls
        and denied_prop is not None
        and denied_prop.ok
        and denied_prop.approval_id is not None
        and create_before_deny == 0
        and denied is not None
        and denied.status == ApprovalStatus.DENIED.value
        and create_after_deny == 0
        and len(vu_deny.gateway.calendar.events) == 0
        and late_exec is not None
        and (not late_exec.ok)
        and len(vu_deny.list_android_approvals()) == 0
    )
    checks.append(
        {
            "id": "e2e-04.deny_creates_nothing",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"deny_status={denied.status if denied else None} "
                f"create_before={create_before_deny} create_after={create_after_deny} "
                f"late={getattr(late_exec, 'reason', None)}"
            ),
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E04Result(
        result=overall,
        checks=checks,
        accept_approval_id=proposed.approval_id if proposed else None,
        deny_approval_id=denied_prop.approval_id if denied_prop else None,
        calendar_create_after_accept=create_after_accept,
        calendar_create_after_deny=create_after_deny,
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        vu.catcher.write_json(out / "outbound-messages.json")
        (out / "calendar.json").write_text(
            json.dumps(
                {
                    "accept_path": {
                        "create_count": create_after_accept,
                        "events": events_after_accept,
                    },
                    "deny_path": {
                        "create_count": create_after_deny,
                        "events": list(vu_deny.gateway.calendar.events),
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (out / "approvals.json").write_text(
            json.dumps(
                {
                    "accept_path": vu.android_inbox.snapshot(),
                    "deny_path": vu_deny.android_inbox.snapshot(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="e2e-04",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-04",
                "gate": True,
                "utterance": utterance,
                "deny_utterance": deny_utterance,
                "accept_approval_id": proposed.approval_id if proposed else None,
                "deny_approval_id": denied_prop.approval_id if denied_prop else None,
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-04",
                        "python3 scripts/run_e2e_04.py",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/e2e-04/",
                },
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-04 calendar soft confirm: WhatsApp 'Schedule focus block "
                        "Friday 09:00–11:00.' proposes pending soft confirm with "
                        "create_count=0; Accept creates event once; Deny path creates "
                        "nothing and late execute is blocked"
                    ),
                    "result": overall,
                    "flow": "E2E-04",
                    "gate": True,
                    "checks": [c["id"] for c in checks],
                    "commands": [
                        "python3 scripts/run_e2e_04.py",
                        "make e2e-04",
                        "./scripts/test-ci.sh",
                        "make test-ci",
                    ],
                    "artifacts": [
                        "artifacts/test/e2e-04/report.json",
                        "artifacts/test/e2e-04/verification.json",
                        "artifacts/test/e2e-04/calendar.json",
                        "artifacts/test/e2e-04/approvals.json",
                        "artifacts/test/e2e-04/outbound-messages.json",
                    ],
                    "accept_approval_id": proposed.approval_id if proposed else None,
                    "deny_approval_id": denied_prop.approval_id if denied_prop else None,
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


def run_e2e_06(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E06Result:
    """E2E-06 — Booksy propose → approve → book (gate-tagged).

    Accept path:
      1. Seed shop prefs + free calendar afternoon.
      2. Text: 'Book a haircut next week afternoon.'
      3. Stub portal returns slots; agent proposes 2–3 options.
      4. book_count = 0 until Accept.
      5. Accept chosen slot → one book + calendar writeback + WhatsApp confirm.

    Deny path (isolated Virtual User):
      Propose → Deny → book_count stays 0; late execute blocked.
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-06")
    checks: list[dict[str, Any]] = []
    utterance = EXPECTED_E2E06_UTTERANCE

    # --- Accept path ---
    vu = VirtualUser.bootstrap(root=repo)
    prefs = (vu.seed_profile.get("preferences") or {}) if vu.seed_profile else {}
    procs = (vu.seed_profile.get("procedures") or {}) if vu.seed_profile else {}
    seed_ok = (
        bool(prefs.get("haircut_style"))
        and "Main St" in str(procs.get("booksy_flow") or "")
        and len(vu.gateway.calendar.events) == 0
        and len(vu.calendar_store.list_all()) == 0
    )
    checks.append(
        {
            "id": "e2e-06.seed_shop_prefs_free_calendar",
            "result": "PASS" if seed_ok else "FAIL",
            "detail": (
                f"haircut={prefs.get('haircut_style')!r} "
                f"booksy={procs.get('booksy_flow')!r} "
                f"events={len(vu.gateway.calendar.events)}"
            ),
            "gate": True,
        }
    )

    turn = vu.inject_text(utterance)
    proposed = vu.last_booking_propose
    propose_ok = (
        turn.allowed
        and "book_propose" in turn.tool_calls
        and proposed is not None
        and proposed.ok
        and not proposed.executed
        and proposed.tier == ApprovalTier.HARD_APPROVE.value
        and proposed.approval_id is not None
        and vu.book_count() == 0
        and 2 <= len(proposed.options) <= 3
        and all(opt.get("period") == "afternoon" for opt in proposed.options)
    )
    checks.append(
        {
            "id": "e2e-06.whatsapp_proposes_slots",
            "result": "PASS" if propose_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} ok={getattr(proposed, 'ok', None)} "
                f"tier={getattr(proposed, 'tier', None)} book={vu.book_count()} "
                f"options={len(proposed.options) if proposed else 0}"
            ),
            "gate": True,
        }
    )

    pending = vu.list_android_approvals()
    pending_ok = (
        len(pending) == 1
        and proposed is not None
        and proposed.approval_id is not None
        and pending[0].id == proposed.approval_id
        and pending[0].action_type == "book"
        and pending[0].status == ApprovalStatus.PENDING.value
        and vu.book_count() == 0
        and vu.calendar_create_count() == 0
    )
    checks.append(
        {
            "id": "e2e-06.pending_hard_approve_book_zero",
            "result": "PASS" if pending_ok else "FAIL",
            "detail": (
                f"pending={len(pending)} book={vu.book_count()} "
                f"calendar={vu.calendar_create_count()}"
            ),
            "gate": True,
        }
    )

    accepted = (
        vu.accept_approval(proposed.approval_id)
        if proposed and proposed.approval_id
        else None
    )
    book_after_accept = vu.book_count()
    calendar_after_accept = vu.calendar_create_count()
    events_after_accept = list(vu.gateway.calendar.events)
    confirms = [
        m for m in vu.catcher.messages if m.meta.get("kind") == "booking_confirm"
    ]
    task = (
        vu.booking_store.get(proposed.task_id)
        if proposed and proposed.task_id
        else None
    )
    accept_ok = (
        accepted is not None
        and accepted.ok
        and accepted.approval.status == ApprovalStatus.EXECUTED.value
        and book_after_accept == 1
        and calendar_after_accept == 1
        and len(events_after_accept) == 1
        and len(confirms) == 1
        and task is not None
        and task.status == BookingStatus.BOOKED
        and task.is_success
        and len(vu.list_android_approvals()) == 0
    )
    checks.append(
        {
            "id": "e2e-06.accept_books_once_writeback",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accepted, 'ok', None)} book={book_after_accept} "
                f"calendar={calendar_after_accept} confirms={len(confirms)} "
                f"task={task.status.value if task else None}"
            ),
            "gate": True,
        }
    )

    # --- Deny path (fresh Virtual User — no prior book writes) ---
    vu_deny = VirtualUser.bootstrap(root=repo)
    deny_turn = vu_deny.inject_text(utterance)
    denied_prop = vu_deny.last_booking_propose
    book_before_deny = vu_deny.book_count()
    denied = (
        vu_deny.deny_approval(denied_prop.approval_id)
        if denied_prop and denied_prop.approval_id
        else None
    )
    book_after_deny = vu_deny.book_count()
    late_exec = (
        vu_deny.gateway.execute(denied_prop.approval_id)
        if denied_prop and denied_prop.approval_id
        else None
    )
    deny_task = (
        vu_deny.booking_store.get(denied_prop.task_id)
        if denied_prop and denied_prop.task_id
        else None
    )
    deny_ok = (
        deny_turn.allowed
        and "book_propose" in deny_turn.tool_calls
        and denied_prop is not None
        and denied_prop.ok
        and denied_prop.approval_id is not None
        and book_before_deny == 0
        and denied is not None
        and denied.status == ApprovalStatus.DENIED.value
        and book_after_deny == 0
        and vu_deny.calendar_create_count() == 0
        and late_exec is not None
        and (not late_exec.ok)
        and deny_task is not None
        and deny_task.status == BookingStatus.DENIED
        and not deny_task.is_success
        and len(vu_deny.list_android_approvals()) == 0
    )
    checks.append(
        {
            "id": "e2e-06.deny_books_nothing",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"deny_status={denied.status if denied else None} "
                f"book_before={book_before_deny} book_after={book_after_deny} "
                f"late={getattr(late_exec, 'reason', None)} "
                f"task={deny_task.status.value if deny_task else None}"
            ),
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E06Result(
        result=overall,
        checks=checks,
        accept_approval_id=proposed.approval_id if proposed else None,
        deny_approval_id=denied_prop.approval_id if denied_prop else None,
        book_count_after_accept=book_after_accept,
        book_count_after_deny=book_after_deny,
        calendar_create_after_accept=calendar_after_accept,
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        vu.catcher.write_json(out / "outbound-messages.json")
        (out / "bookings.json").write_text(
            json.dumps(
                {
                    "accept_path": {
                        "book_count": book_after_accept,
                        "calendar_create_count": calendar_after_accept,
                        "events": events_after_accept,
                        "task": task.to_dict() if task else None,
                        "options": proposed.options if proposed else [],
                        "confirms": len(confirms),
                    },
                    "deny_path": {
                        "book_count": book_after_deny,
                        "calendar_create_count": vu_deny.calendar_create_count(),
                        "task": deny_task.to_dict() if deny_task else None,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (out / "approvals.json").write_text(
            json.dumps(
                {
                    "accept_path": vu.android_inbox.snapshot(),
                    "deny_path": vu_deny.android_inbox.snapshot(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="e2e-06",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-06",
                "gate": True,
                "utterance": utterance,
                "accept_approval_id": proposed.approval_id if proposed else None,
                "deny_approval_id": denied_prop.approval_id if denied_prop else None,
                "book_count_after_accept": book_after_accept,
                "book_count_after_deny": book_after_deny,
                "t5_exit": overall == "PASS",
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-06",
                        "python3 scripts/run_e2e_06.py",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/e2e-06/",
                },
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-06 Booksy propose→approve→book: WhatsApp "
                        f"{utterance!r} proposes 2–3 afternoon slots with "
                        "book_count=0; Accept books once + calendar writeback + "
                        "WhatsApp confirm; Deny leaves book_count=0 and late "
                        "execute blocked (T5 exit)"
                    ),
                    "result": overall,
                    "flow": "E2E-06",
                    "gate": True,
                    "t5_exit": overall == "PASS",
                    "checks": [c["id"] for c in checks],
                    "commands": [
                        "python3 scripts/run_e2e_06.py",
                        "make e2e-06",
                        "./scripts/test-ci.sh",
                        "make test-ci",
                    ],
                    "artifacts": [
                        "artifacts/test/e2e-06/report.json",
                        "artifacts/test/e2e-06/verification.json",
                        "artifacts/test/e2e-06/bookings.json",
                        "artifacts/test/e2e-06/approvals.json",
                        "artifacts/test/e2e-06/outbound-messages.json",
                    ],
                    "accept_approval_id": proposed.approval_id if proposed else None,
                    "deny_approval_id": denied_prop.approval_id if denied_prop else None,
                    "book_count_after_accept": book_after_accept,
                    "book_count_after_deny": book_after_deny,
                    "calendar_create_after_accept": calendar_after_accept,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return result


def run_e2e_07(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E07Result:
    """E2E-07 — Shopping with cap / freeze (gate-tagged; deny path for merge gate).

    Spec (agent-plan/testing/e2e-flows.md):
      1. “Buy my usual protein powder.”
      2. Proposal shows price; execute = 0.
      3. Accept under cap → dry-run purchase logged.
      4. Repeat with freeze on → execute blocked.
      5. Repeat over cap → blocked with cap reason.

    Deny path (isolated Virtual User): Propose → Deny → buy_count stays 0.
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-07")
    checks: list[dict[str, Any]] = []
    utterance = EXPECTED_E2E07_UTTERANCE

    # --- Accept under cap ---
    vu = VirtualUser.bootstrap(root=repo)
    prefs = (vu.seed_profile.get("preferences") or {}) if vu.seed_profile else {}
    usual = dict(prefs.get("usual_purchases") or {})
    seed_ok = (
        bool(usual.get("protein_powder"))
        or vu.shopping.merchant.find_usual("protein_powder") is not None
    )
    checks.append(
        {
            "id": "e2e-07.seed_usual_protein",
            "result": "PASS" if seed_ok else "FAIL",
            "detail": (
                f"profile_usual={usual.get('protein_powder')!r} "
                f"catalog_usual={vu.shopping.merchant.find_usual('protein_powder')}"
            ),
            "gate": True,
        }
    )

    turn = vu.inject_text(utterance)
    proposed = vu.last_shopping_propose
    propose_ok = (
        turn.allowed
        and "buy_propose" in turn.tool_calls
        and proposed is not None
        and proposed.ok
        and not proposed.executed
        and proposed.tier == ApprovalTier.HARD_APPROVE.value
        and proposed.approval_id is not None
        and proposed.price == 29.99
        and vu.buy_count() == 0
        and proposed.buy_count_at_propose == 0
    )
    checks.append(
        {
            "id": "e2e-07.propose_shows_price_buy_zero",
            "result": "PASS" if propose_ok else "FAIL",
            "detail": (
                f"tools={turn.tool_calls} ok={getattr(proposed, 'ok', None)} "
                f"price={getattr(proposed, 'price', None)} buy={vu.buy_count()} "
                f"tier={getattr(proposed, 'tier', None)}"
            ),
            "gate": True,
        }
    )

    pending = vu.list_android_approvals()
    pending_ok = (
        len(pending) == 1
        and proposed is not None
        and proposed.approval_id is not None
        and pending[0].id == proposed.approval_id
        and pending[0].action_type == "buy"
        and pending[0].status == ApprovalStatus.PENDING.value
        and vu.buy_count() == 0
    )
    checks.append(
        {
            "id": "e2e-07.pending_hard_approve_buy_zero",
            "result": "PASS" if pending_ok else "FAIL",
            "detail": (
                f"pending={len(pending)} buy={vu.buy_count()} "
                f"action={pending[0].action_type if pending else None}"
            ),
            "gate": True,
        }
    )

    accepted = (
        vu.accept_approval(proposed.approval_id)
        if proposed and proposed.approval_id
        else None
    )
    buy_after_accept = vu.buy_count()
    receipts = [
        m for m in vu.catcher.messages if m.meta.get("kind") == "shopping_receipt"
    ]
    task = (
        vu.purchase_store.get(proposed.task_id)
        if proposed and proposed.task_id
        else None
    )
    audits = (
        vu.gateway.audit.for_approval(proposed.approval_id)
        if proposed and proposed.approval_id
        else []
    )
    accept_ok = (
        accepted is not None
        and accepted.ok
        and accepted.approval.status == ApprovalStatus.EXECUTED.value
        and buy_after_accept == 1
        and len(receipts) == 1
        and task is not None
        and task.status == PurchaseStatus.PURCHASED
        and task.is_success
        and isinstance(accepted.execute.result if accepted.execute else None, dict)
        and (accepted.execute.result or {}).get("dry_run") is True
        and any(a.success and a.approval_id == proposed.approval_id for a in audits)
        and len(vu.list_android_approvals()) == 0
        and len(vu.gateway.spend.entries) == 1
    )
    checks.append(
        {
            "id": "e2e-07.accept_under_cap_dry_run",
            "result": "PASS" if accept_ok else "FAIL",
            "detail": (
                f"accept_ok={getattr(accepted, 'ok', None)} buy={buy_after_accept} "
                f"receipts={len(receipts)} task={task.status.value if task else None} "
                f"audits={len(audits)} dry_run="
                f"{(accepted.execute.result or {}).get('dry_run') if accepted and accepted.execute and isinstance(accepted.execute.result, dict) else None}"
            ),
            "gate": True,
        }
    )

    # --- Freeze path (INV-PAY-001): stale accepted approval blocked ---
    vu_freeze = VirtualUser.bootstrap(root=repo)
    freeze_turn = vu_freeze.inject_text(utterance)
    freeze_prop = vu_freeze.last_shopping_propose
    freeze_reason: Optional[str] = None
    freeze_status: Optional[str] = None
    if freeze_prop and freeze_prop.approval_id:
        vu_freeze.gateway.accept(freeze_prop.approval_id)
        vu_freeze.gateway.freeze_spending()
        blocked_f = vu_freeze.gateway.execute(freeze_prop.approval_id)
        freeze_reason = blocked_f.reason
        item_f = vu_freeze.gateway.approvals.get(freeze_prop.approval_id)
        freeze_status = item_f.status.value if item_f else None
    buy_after_freeze = vu_freeze.buy_count()
    freeze_ok = (
        freeze_turn.allowed
        and "buy_propose" in freeze_turn.tool_calls
        and freeze_prop is not None
        and freeze_prop.ok
        and freeze_prop.approval_id is not None
        and freeze_reason == "freeze_spending"
        and buy_after_freeze == 0
        and freeze_status == ApprovalStatus.ACCEPTED.value
        and any(
            r.get("reason") == "freeze_spending"
            for r in vu_freeze.gateway.execute_rejections
        )
    )
    checks.append(
        {
            "id": "e2e-07.freeze_blocks_execute",
            "result": "PASS" if freeze_ok else "FAIL",
            "detail": (
                f"reason={freeze_reason} buy={buy_after_freeze} "
                f"status={freeze_status} "
                f"rejections={len(vu_freeze.gateway.execute_rejections)}"
            ),
            "gate": True,
        }
    )

    # --- Over cap path (INV-PAY-002) ---
    vu_cap = VirtualUser.bootstrap(root=repo)
    vu_cap.gateway.spend.config = SpendCapConfig(
        daily_limit=10.0, weekly_limit=150.0, currency="EUR"
    )
    vu_cap.shopping.spend_caps = vu_cap.gateway.spend.config
    cap_turn = vu_cap.inject_text(utterance)
    cap_prop = vu_cap.last_shopping_propose
    cap_accept = (
        vu_cap.accept_approval(cap_prop.approval_id)
        if cap_prop and cap_prop.approval_id
        else None
    )
    cap_reason = (
        cap_accept.execute.reason
        if cap_accept and cap_accept.execute
        else getattr(cap_accept, "reason", None)
    )
    buy_after_cap = vu_cap.buy_count()
    cap_ok = (
        cap_turn.allowed
        and "buy_propose" in cap_turn.tool_calls
        and cap_prop is not None
        and cap_prop.ok
        and cap_prop.price == 29.99
        and cap_accept is not None
        and (not cap_accept.ok)
        and cap_reason == "spend_cap_daily"
        and buy_after_cap == 0
        and any(
            r.get("reason") == "spend_cap_daily"
            for r in vu_cap.gateway.execute_rejections
        )
    )
    checks.append(
        {
            "id": "e2e-07.over_cap_blocked",
            "result": "PASS" if cap_ok else "FAIL",
            "detail": (
                f"reason={cap_reason} buy={buy_after_cap} "
                f"price={getattr(cap_prop, 'price', None)} "
                f"rejections={len(vu_cap.gateway.execute_rejections)}"
            ),
            "gate": True,
        }
    )

    # --- Deny path (merge gate) ---
    vu_deny = VirtualUser.bootstrap(root=repo)
    deny_turn = vu_deny.inject_text(utterance)
    denied_prop = vu_deny.last_shopping_propose
    buy_before_deny = vu_deny.buy_count()
    denied = (
        vu_deny.deny_approval(denied_prop.approval_id)
        if denied_prop and denied_prop.approval_id
        else None
    )
    buy_after_deny = vu_deny.buy_count()
    late_exec = (
        vu_deny.gateway.execute(denied_prop.approval_id)
        if denied_prop and denied_prop.approval_id
        else None
    )
    deny_task = (
        vu_deny.purchase_store.get(denied_prop.task_id)
        if denied_prop and denied_prop.task_id
        else None
    )
    deny_ok = (
        deny_turn.allowed
        and "buy_propose" in deny_turn.tool_calls
        and denied_prop is not None
        and denied_prop.ok
        and denied_prop.approval_id is not None
        and buy_before_deny == 0
        and denied is not None
        and denied.status == ApprovalStatus.DENIED.value
        and buy_after_deny == 0
        and late_exec is not None
        and (not late_exec.ok)
        and deny_task is not None
        and deny_task.status == PurchaseStatus.DENIED
        and not deny_task.is_success
        and len(vu_deny.list_android_approvals()) == 0
    )
    checks.append(
        {
            "id": "e2e-07.deny_buys_nothing",
            "result": "PASS" if deny_ok else "FAIL",
            "detail": (
                f"deny_status={denied.status if denied else None} "
                f"buy_before={buy_before_deny} buy_after={buy_after_deny} "
                f"late={getattr(late_exec, 'reason', None)} "
                f"task={deny_task.status.value if deny_task else None}"
            ),
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E07Result(
        result=overall,
        checks=checks,
        accept_approval_id=proposed.approval_id if proposed else None,
        deny_approval_id=denied_prop.approval_id if denied_prop else None,
        freeze_approval_id=freeze_prop.approval_id if freeze_prop else None,
        cap_approval_id=cap_prop.approval_id if cap_prop else None,
        buy_count_after_accept=buy_after_accept,
        buy_count_after_deny=buy_after_deny,
        buy_count_after_freeze=buy_after_freeze,
        buy_count_after_cap=buy_after_cap,
        proposed_price=proposed.price if proposed else None,
        freeze_reason=freeze_reason,
        cap_reason=str(cap_reason) if cap_reason else None,
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        vu.catcher.write_json(out / "outbound-messages.json")
        (out / "purchases.json").write_text(
            json.dumps(
                {
                    "accept_path": {
                        "buy_count": buy_after_accept,
                        "price": proposed.price if proposed else None,
                        "task": task.to_dict() if task else None,
                        "receipts": len(receipts),
                        "audits": [a.to_dict() for a in audits] if audits else [],
                        "spend_entries": len(vu.gateway.spend.entries),
                    },
                    "freeze_path": {
                        "buy_count": buy_after_freeze,
                        "reason": freeze_reason,
                        "approval_status": freeze_status,
                        "rejections": list(vu_freeze.gateway.execute_rejections),
                    },
                    "cap_path": {
                        "buy_count": buy_after_cap,
                        "reason": cap_reason,
                        "daily_limit": vu_cap.gateway.spend.config.daily_limit,
                        "rejections": list(vu_cap.gateway.execute_rejections),
                    },
                    "deny_path": {
                        "buy_count": buy_after_deny,
                        "task": deny_task.to_dict() if deny_task else None,
                        "late_execute_reason": getattr(late_exec, "reason", None),
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (out / "approvals.json").write_text(
            json.dumps(
                {
                    "accept_path": vu.android_inbox.snapshot(),
                    "freeze_path": vu_freeze.android_inbox.snapshot(),
                    "cap_path": vu_cap.android_inbox.snapshot(),
                    "deny_path": vu_deny.android_inbox.snapshot(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (out / "audit.json").write_text(
            json.dumps(
                {
                    "accept_audits": [a.to_dict() for a in audits] if audits else [],
                    "freeze_rejections": list(vu_freeze.gateway.execute_rejections),
                    "cap_rejections": list(vu_cap.gateway.execute_rejections),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="e2e-07",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-07",
                "gate": True,
                "utterance": utterance,
                "accept_approval_id": proposed.approval_id if proposed else None,
                "deny_approval_id": denied_prop.approval_id if denied_prop else None,
                "freeze_approval_id": freeze_prop.approval_id if freeze_prop else None,
                "cap_approval_id": cap_prop.approval_id if cap_prop else None,
                "buy_count_after_accept": buy_after_accept,
                "buy_count_after_deny": buy_after_deny,
                "buy_count_after_freeze": buy_after_freeze,
                "buy_count_after_cap": buy_after_cap,
                "proposed_price": proposed.price if proposed else None,
                "freeze_reason": freeze_reason,
                "cap_reason": cap_reason,
                "t6_exit": overall == "PASS",
                "invariants": ["INV-PAY-001", "INV-PAY-002"],
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "./scripts/test-ci.sh",
                        "make test-ci",
                        "make e2e-07",
                        "python3 scripts/run_e2e_07.py",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/e2e-07/",
                },
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-07 Shopping with cap/freeze: WhatsApp "
                        f"{utterance!r} proposes hard approve with price "
                        "and buy_count=0; Accept under cap → one dry-run "
                        "purchase + receipt/audit; freeze blocks execute "
                        "(stale accepted, not cancelled); over cap → "
                        "spend_cap_daily + buy=0; Deny leaves buy_count=0 "
                        "(T6 exit / merge gate deny path)"
                    ),
                    "result": overall,
                    "flow": "E2E-07",
                    "gate": True,
                    "t6_exit": overall == "PASS",
                    "checks": [c["id"] for c in checks],
                    "invariants": ["INV-PAY-001", "INV-PAY-002"],
                    "commands": [
                        "python3 scripts/run_e2e_07.py",
                        "make e2e-07",
                        "./scripts/test-ci.sh",
                        "make test-ci",
                    ],
                    "artifacts": [
                        "artifacts/test/e2e-07/report.json",
                        "artifacts/test/e2e-07/verification.json",
                        "artifacts/test/e2e-07/purchases.json",
                        "artifacts/test/e2e-07/approvals.json",
                        "artifacts/test/e2e-07/audit.json",
                        "artifacts/test/e2e-07/outbound-messages.json",
                    ],
                    "accept_approval_id": proposed.approval_id if proposed else None,
                    "deny_approval_id": denied_prop.approval_id if denied_prop else None,
                    "buy_count_after_accept": buy_after_accept,
                    "buy_count_after_deny": buy_after_deny,
                    "buy_count_after_freeze": buy_after_freeze,
                    "buy_count_after_cap": buy_after_cap,
                    "proposed_price": proposed.price if proposed else None,
                    "freeze_reason": freeze_reason,
                    "cap_reason": cap_reason,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return result


def run_e2e_09(
    *,
    root: Path | None = None,
    artifacts_dir: Path | None = None,
    write_artifacts: bool = True,
) -> E2E09Result:
    """E2E-09 — Ignored hard approval expires (execute stays 0).

    1. Create booking approval (hard).
    2. Advance clock past expiry (default hard TTL 4h).
    3. Attempt late Accept / execute → blocked; book_count still 0.
    """
    repo = root or ROOT
    out = artifacts_dir or (repo / "artifacts" / "test" / "e2e-09")
    checks: list[dict[str, Any]] = []
    utterance = EXPECTED_E2E06_UTTERANCE

    vu = VirtualUser.bootstrap(root=repo)
    proposed = vu.book_from_utterance(utterance)
    book_at_propose = vu.book_count()
    propose_ok = (
        proposed.ok
        and proposed.approval_id is not None
        and proposed.tier == ApprovalTier.HARD_APPROVE.value
        and not proposed.executed
        and book_at_propose == 0
        and len(vu.pending_approvals()) == 1
    )
    checks.append(
        {
            "id": "e2e-09.booking_approval_pending",
            "result": "PASS" if propose_ok else "FAIL",
            "detail": (
                f"ok={proposed.ok} approval_id={proposed.approval_id} "
                f"book={book_at_propose} pending={len(vu.pending_approvals())}"
            ),
            "gate": True,
        }
    )

    item_before = (
        vu.gateway.approvals.get(proposed.approval_id) if proposed.approval_id else None
    )
    status_before = item_before.status if item_before else None
    expires_at_before = item_before.expires_at if item_before else None
    vu.advance(timedelta(hours=5))
    expired_list = vu.gateway.approvals.expire_due()
    expired_item = (
        vu.gateway.approvals.get(proposed.approval_id) if proposed.approval_id else None
    )
    expire_ok = (
        item_before is not None
        and status_before == ApprovalStatus.PENDING
        and expired_item is not None
        and expired_item.status == ApprovalStatus.EXPIRED
        and any(e.id == proposed.approval_id for e in expired_list)
        and vu.book_count() == 0
    )
    checks.append(
        {
            "id": "e2e-09.clock_past_expiry",
            "result": "PASS" if expire_ok else "FAIL",
            "detail": (
                f"before={status_before.value if status_before else None} "
                f"after={expired_item.status.value if expired_item else None} "
                f"expires_at={expires_at_before.isoformat() if expires_at_before else None} "
                f"expired_n={len(expired_list)} book={vu.book_count()}"
            ),
            "gate": True,
        }
    )

    late_accept_ok: bool | None = None
    late_accept_err: str | None = None
    if proposed.approval_id:
        try:
            late_accept = vu.accept_approval(proposed.approval_id)
            late_accept_ok = late_accept.ok
        except ApprovalError as exc:
            late_accept_ok = False
            late_accept_err = str(exc)
    late_exec = (
        vu.gateway.execute(proposed.approval_id) if proposed.approval_id else None
    )
    late_ok = (
        late_accept_ok is False
        and late_exec is not None
        and (not late_exec.ok)
        and vu.book_count() == 0
        and vu.calendar_create_count() == 0
        and expired_item is not None
        and expired_item.status == ApprovalStatus.EXPIRED
    )
    checks.append(
        {
            "id": "e2e-09.late_accept_execute_blocked",
            "result": "PASS" if late_ok else "FAIL",
            "detail": (
                f"late_accept_ok={late_accept_ok} err={late_accept_err!r} "
                f"late_exec={getattr(late_exec, 'reason', None)} "
                f"book={vu.book_count()} calendar={vu.calendar_create_count()}"
            ),
            "gate": True,
        }
    )

    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    result = E2E09Result(
        result=overall,
        checks=checks,
        approval_id=proposed.approval_id,
        status=expired_item.status.value if expired_item else None,
        book_count=vu.book_count(),
        artifacts_dir=str(out.relative_to(repo)) if out.is_relative_to(repo) else str(out),
    )

    if write_artifacts:
        out.mkdir(parents=True, exist_ok=True)
        vu.catcher.write_json(out / "outbound-messages.json")
        (out / "approvals.json").write_text(
            json.dumps(
                {
                    "approval_id": proposed.approval_id,
                    "status_before": status_before.value if status_before else None,
                    "status_after": expired_item.status.value if expired_item else None,
                    "expires_at": (
                        expired_item.expires_at.isoformat()
                        if expired_item and expired_item.expires_at
                        else None
                    ),
                    "snapshot": vu.android_inbox.snapshot(),
                    "all": [a.to_dict() for a in vu.gateway.approvals.list()],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (out / "bookings.json").write_text(
            json.dumps(
                {
                    "book_count": vu.book_count(),
                    "calendar_create_count": vu.calendar_create_count(),
                    "tasks": vu.booking_store.to_dict(),
                    "late_accept_ok": late_accept_ok,
                    "late_exec_reason": getattr(late_exec, "reason", None),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_report(
            out,
            layer="e2e-09",
            result=overall,
            checks=checks,
            extra={
                "flow": "E2E-09",
                "gate": True,
                "utterance": utterance,
                "approval_id": proposed.approval_id,
                "status": expired_item.status.value if expired_item else None,
                "book_count": vu.book_count(),
                "harness": "VirtualUser",
                "agent_b_rerun": {
                    "happy_path": [
                        "make e2e-09",
                        "python3 scripts/run_e2e_09.py",
                        "./scripts/test-ci.sh",
                    ],
                    "fail_closed_proof": [
                        "./scripts/test-ci.sh --break-invariant",
                        "make test-ci-fail-closed",
                    ],
                    "artifacts": "artifacts/test/e2e-09/",
                },
            },
        )
        (out / "verification.json").write_text(
            json.dumps(
                {
                    "claim": (
                        "E2E-09 ignored hard approval expires: booking hard approve "
                        "pending → FakeClock +5h → status expired; late Accept/execute "
                        "blocked; book_count stays 0"
                    ),
                    "result": overall,
                    "flow": "E2E-09",
                    "gate": True,
                    "checks": [c["id"] for c in checks],
                    "commands": [
                        "python3 scripts/run_e2e_09.py",
                        "make e2e-09",
                        "./scripts/test-ci.sh",
                        "make test-ci",
                    ],
                    "artifacts": [
                        "artifacts/test/e2e-09/report.json",
                        "artifacts/test/e2e-09/verification.json",
                        "artifacts/test/e2e-09/approvals.json",
                        "artifacts/test/e2e-09/bookings.json",
                        "artifacts/test/e2e-09/outbound-messages.json",
                    ],
                    "approval_id": proposed.approval_id,
                    "status": expired_item.status.value if expired_item else None,
                    "book_count": vu.book_count(),
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
