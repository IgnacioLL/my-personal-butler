"""Diet planning service — plan meals, validate constraints, emit grocery todos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from capabilities.calendar.store import CalendarStore
from capabilities.diet.constraints import check_meal_plan
from capabilities.diet.eval import DietEvalResult, evaluate_plan_quality
from capabilities.diet.parse import ParsedMealPlanRequest, parse_meal_plan_request
from capabilities.diet.planner import build_meal_plan
from capabilities.diet.store import MealPlan
from capabilities.todos.store import Todo, TodoSource, TodoStore
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from intelligence.memory.store import MemoryStore
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalTier, tier_for


@dataclass
class PlanMealsResult:
    ok: bool
    plan: Optional[MealPlan]
    parsed: Optional[ParsedMealPlanRequest]
    confirm_body: str
    tier: str
    reason: str
    grocery_todos: list[Todo] = field(default_factory=list)
    constraint_ok: bool = False
    eval_result: Optional[DietEvalResult] = None
    gateway_result: Optional[ProposeResult] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "plan": self.plan.to_dict() if self.plan else None,
            "parsed": (
                {
                    "target_phrase": self.parsed.target_phrase,
                    "plan_date": self.parsed.plan_date.isoformat(),
                }
                if self.parsed
                else None
            ),
            "confirm_body": self.confirm_body,
            "tier": self.tier,
            "reason": self.reason,
            "grocery_todo_ids": [t.id for t in self.grocery_todos],
            "constraint_ok": self.constraint_ok,
            "eval": self.eval_result.to_dict() if self.eval_result else None,
        }


def constraints_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    prefs = profile.get("preferences") or {}
    goals = profile.get("goals") or {}
    return {
        "allergies": list(prefs.get("allergies") or []),
        "food_dislikes": list(prefs.get("food_dislikes") or []),
        "food_likes": list(prefs.get("food_likes") or []),
        "diet_phase": goals.get("diet_phase") or "",
        "quiet_hours": prefs.get("quiet_hours") or {},
    }


class DietService:
    """Generate meal plans from memory + calendar; create grocery todos (Auto)."""

    def __init__(
        self,
        *,
        calendar: CalendarStore,
        todo_store: TodoStore,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        memory: MemoryStore | None = None,
        constraints: dict[str, Any] | None = None,
        gateway: ActionGateway | None = None,
        timezone: str = "UTC",
        recipient: str = "",
    ) -> None:
        self.calendar = calendar
        self.todo_store = todo_store
        self.clock = clock
        self.catcher = catcher
        self.memory = memory
        self._constraints = constraints
        self.gateway = gateway
        self.timezone = timezone
        self.recipient = recipient
        if self.gateway is not None:
            self.gateway.todos = self.todo_store

    def _load_constraints(self) -> dict[str, Any]:
        if self.memory is not None:
            return self.memory.planning_constraints()
        return dict(self._constraints or {})

    def plan_from_utterance(
        self,
        utterance: str,
        *,
        recipient: str | None = None,
        timezone: str | None = None,
    ) -> PlanMealsResult:
        to = recipient if recipient is not None else self.recipient
        tz = timezone or self.timezone
        now = self.clock.now()
        tier = tier_for("diet_draft")
        if tier != ApprovalTier.AUTO:
            return PlanMealsResult(
                ok=False,
                plan=None,
                parsed=None,
                confirm_body="",
                tier=tier.value,
                reason=f"expected_auto_tier_got_{tier.value}",
            )

        try:
            parsed = parse_meal_plan_request(utterance, now=now)
        except ValueError as exc:
            return PlanMealsResult(
                ok=False,
                plan=None,
                parsed=None,
                confirm_body="",
                tier=tier.value,
                reason=f"parse_error:{exc}",
            )

        constraints = self._load_constraints()
        try:
            plan = build_meal_plan(
                plan_date=parsed.plan_date,
                timezone=tz,
                constraints=constraints,
                calendar=self.calendar,
            )
        except ValueError as exc:
            return PlanMealsResult(
                ok=False,
                plan=None,
                parsed=parsed,
                confirm_body="",
                tier=tier.value,
                reason=f"planner_error:{exc}",
            )

        check = check_meal_plan(
            meals=[m.to_dict() for m in plan.meals],
            grocery_items=plan.grocery_items,
            constraints=constraints,
        )
        if not check.ok:
            return PlanMealsResult(
                ok=False,
                plan=plan,
                parsed=parsed,
                confirm_body="",
                tier=tier.value,
                reason=f"constraint_violation:{','.join(check.violations)}",
                constraint_ok=False,
            )

        eval_result = evaluate_plan_quality(plan.to_dict())

        gw_result: ProposeResult | None = None
        if self.gateway is not None:
            gw_result = self.gateway.propose(
                "diet_draft",
                f"Meal plan for {parsed.plan_date.isoformat()}",
                {"plan": plan.to_dict(), "utterance": utterance},
            )
            if not gw_result.ok:
                return PlanMealsResult(
                    ok=False,
                    plan=plan,
                    parsed=parsed,
                    confirm_body="",
                    tier=gw_result.tier or tier.value,
                    reason=gw_result.reason,
                    constraint_ok=True,
                    eval_result=eval_result,
                    gateway_result=gw_result,
                )

        grocery_todos = self._create_grocery_todos(plan, now=now)
        confirm = self._format_confirm(plan)
        self.catcher.send(
            "whatsapp",
            to or "owner",
            confirm,
            ts=now,
            kind="diet_plan",
            plan_date=plan.plan_date.isoformat(),
            grocery_count=len(grocery_todos),
        )
        return PlanMealsResult(
            ok=True,
            plan=plan,
            parsed=parsed,
            confirm_body=confirm,
            tier=tier.value,
            reason="planned",
            grocery_todos=grocery_todos,
            constraint_ok=True,
            eval_result=eval_result,
            gateway_result=gw_result,
        )

    def _create_grocery_todos(self, plan: MealPlan, *, now: datetime) -> list[Todo]:
        created: list[Todo] = []
        for item in plan.grocery_items:
            title = f"Buy {item}"
            existing = self.todo_store.find_open_duplicate(title)
            if existing is not None:
                created.append(existing)
                continue
            if self.gateway is not None:
                gw = self.gateway.propose(
                    "todo_add",
                    f"Grocery: {item}",
                    {
                        "title": title,
                        "created_from": TodoSource.AGENT.value,
                        "tags": ["grocery", "diet"],
                        "notes": f"For meal plan {plan.plan_date.isoformat()}",
                    },
                )
                if gw.ok and gw.executed and gw.auto_result:
                    todo_id = gw.auto_result.get("todo_id")
                    todo = self.todo_store.get(str(todo_id)) if todo_id else None
                    if todo is not None:
                        created.append(todo)
                        continue
            todo = self.todo_store.create(
                title=title,
                created_at=now,
                created_from=TodoSource.AGENT,
                tags=["grocery", "diet"],
                notes=f"For meal plan {plan.plan_date.isoformat()}",
            )
            created.append(todo)
        return created

    def _format_confirm(self, plan: MealPlan) -> str:
        lines = [f"Meal plan for {plan.plan_date.strftime('%A %Y-%m-%d')}:"]
        for meal in plan.meals:
            lines.append(f"- {meal.slot.title()}: {meal.name}")
        if plan.schedule_notes:
            lines.append("Schedule: " + "; ".join(plan.schedule_notes))
        lines.append(f"Grocery list: {len(plan.grocery_items)} items → todos created.")
        return "\n".join(lines)
