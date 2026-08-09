"""Shopping service — dry-run merchant → hard approve → purchase + receipt."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from capabilities.shopping.merchant import DryRunMerchant, MerchantProduct
from capabilities.shopping.parse import (
    ParsedShoppingRequest,
    looks_like_shopping,
    parse_shopping,
)
from capabilities.shopping.store import PurchaseStatus, PurchaseStore, PurchaseTask
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalTier, tier_for
from policy.spend_caps import SpendCapConfig

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MERCHANT_FIXTURE = ROOT / "fixtures" / "shopping" / "merchant-catalog.json"
DEFAULT_CAPS_CONFIG = ROOT / "config" / "shopping.harness.json"


@dataclass
class ProposePurchaseResult:
    ok: bool
    parsed: Optional[ParsedShoppingRequest]
    approval_id: Optional[str]
    task_id: Optional[str]
    tier: str
    reason: str
    confirm_body: str
    price: Optional[float] = None
    currency: str = "EUR"
    merchant: Optional[str] = None
    sku: Optional[str] = None
    options: list[dict[str, Any]] = field(default_factory=list)
    gateway_result: Optional[ProposeResult] = None
    executed: bool = False
    buy_count_at_propose: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "tier": self.tier,
            "reason": self.reason,
            "confirm_body": self.confirm_body,
            "price": self.price,
            "currency": self.currency,
            "merchant": self.merchant,
            "sku": self.sku,
            "options": list(self.options),
            "executed": self.executed,
            "buy_count_at_propose": self.buy_count_at_propose,
            "parsed": (
                {
                    "item_key": self.parsed.item_key,
                    "product_query": self.parsed.product_query,
                    "prefer_usual": self.parsed.prefer_usual,
                    "raw": self.parsed.raw,
                }
                if self.parsed
                else None
            ),
        }


def _format_propose(
    *,
    product: MerchantProduct,
    options: list[dict[str, Any]],
) -> str:
    lines = [
        (
            f"Proposed purchase: {product.name} ({product.brand}, {product.size}) "
            f"at {product.merchant} — {product.price:g} {product.currency}. "
            f"Hard approve required (dry-run merchant)."
        )
    ]
    if len(options) > 1:
        lines.append("Options:")
        for i, opt in enumerate(options, start=1):
            lines.append(
                f"  {i}) {opt.get('name')} — {opt.get('price'):g} {opt.get('currency')}"
            )
    return "\n".join(lines)


class ShoppingService:
    """Propose dry-run purchase (Hard approve). Execute only after Accept under caps."""

    def __init__(
        self,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        gateway: ActionGateway | None = None,
        merchant: DryRunMerchant | None = None,
        store: PurchaseStore | None = None,
        spend_caps: SpendCapConfig | None = None,
        recipient: str = "",
        option_limit: int = 3,
        merchant_fixture: Path | str | None = None,
        caps_config: Path | str | None = None,
        usual_from_profile: dict[str, Any] | None = None,
    ) -> None:
        self.clock = clock
        self.catcher = catcher
        self.gateway = gateway
        self.store = store if store is not None else PurchaseStore()
        self.recipient = recipient
        self.option_limit = option_limit
        self.usual_from_profile = dict(usual_from_profile or {})
        if merchant is not None:
            self.merchant = merchant
        else:
            fixture = Path(merchant_fixture) if merchant_fixture else DEFAULT_MERCHANT_FIXTURE
            self.merchant = (
                DryRunMerchant.from_fixture(fixture)
                if fixture.is_file()
                else DryRunMerchant()
            )
        if spend_caps is not None:
            self.spend_caps = spend_caps
        else:
            caps_path = Path(caps_config) if caps_config else DEFAULT_CAPS_CONFIG
            self.spend_caps = (
                SpendCapConfig.from_file(caps_path)
                if caps_path.is_file()
                else SpendCapConfig()
            )
        if self.gateway is not None:
            self.gateway.attach_shopping(
                self.store,
                outbound=self.catcher,
                spend_caps=self.spend_caps,
            )

    def propose_from_utterance(
        self,
        utterance: str,
        *,
        recipient: str | None = None,
        source_channel: str = "whatsapp",
        chosen_index: int = 0,
    ) -> ProposePurchaseResult:
        """Parse NL → catalog match → pending hard approve. buy_count stays 0."""
        to = recipient if recipient is not None else self.recipient
        tier = tier_for("buy")
        if tier != ApprovalTier.HARD_APPROVE:
            return ProposePurchaseResult(
                ok=False,
                parsed=None,
                approval_id=None,
                task_id=None,
                tier=tier.value,
                reason=f"expected_hard_approve_got_{tier.value}",
                confirm_body="",
            )

        try:
            parsed = parse_shopping(utterance)
        except ValueError as exc:
            return ProposePurchaseResult(
                ok=False,
                parsed=None,
                approval_id=None,
                task_id=None,
                tier=tier.value,
                reason=f"parse_error:{exc}",
                confirm_body="",
            )

        return self.propose_for_request(
            parsed,
            recipient=to,
            source_channel=source_channel,
            source_utterance=utterance,
            chosen_index=chosen_index,
        )

    def propose_for_request(
        self,
        parsed: ParsedShoppingRequest,
        *,
        recipient: str = "",
        source_channel: str = "whatsapp",
        source_utterance: str | None = None,
        chosen_index: int = 0,
    ) -> ProposePurchaseResult:
        tier = tier_for("buy")
        matches = self.merchant.search(
            query=parsed.product_query,
            item_key=parsed.item_key,
            prefer_usual=parsed.prefer_usual,
            limit=self.option_limit,
        )
        if not matches and parsed.prefer_usual:
            usual = self.merchant.find_usual(parsed.item_key)
            if usual is not None:
                matches = [usual]

        if not matches:
            return ProposePurchaseResult(
                ok=False,
                parsed=parsed,
                approval_id=None,
                task_id=None,
                tier=tier.value,
                reason="no_products_found",
                confirm_body="",
            )

        options = [p.to_dict() for p in matches[: self.option_limit]]
        idx = max(0, min(chosen_index, len(options) - 1))
        chosen = matches[idx]
        # Profile usual override (brand/sku hint) — still no execute.
        profile_usual = self.usual_from_profile.get(parsed.item_key) or {}
        if isinstance(profile_usual, dict) and profile_usual.get("sku"):
            for i, product in enumerate(matches):
                if product.sku == profile_usual.get("sku"):
                    idx = i
                    chosen = product
                    break

        task = self.store.create(
            merchant=chosen.merchant,
            sku=chosen.sku,
            name=chosen.name,
            price=chosen.price,
            currency=chosen.currency,
            options=options,
            status=PurchaseStatus.PROPOSED,
            chosen_index=idx,
            created_at=self.clock.now(),
            meta={
                "item_key": parsed.item_key,
                "prefer_usual": parsed.prefer_usual,
                "dry_run": True,
            },
        )

        payload: dict[str, Any] = {
            "purchase_task_id": task.id,
            "sku": chosen.sku,
            "name": chosen.name,
            "brand": chosen.brand,
            "size": chosen.size,
            "price": chosen.price,
            "currency": chosen.currency,
            "merchant": chosen.merchant,
            "merchant_url": self.merchant.merchant_url,
            "options": options,
            "chosen_index": idx,
            "item_key": parsed.item_key,
            "dry_run": True,
            "recipient": recipient,
        }

        summary = (
            f"Buy {chosen.name} at {chosen.merchant} "
            f"for {chosen.price:g} {chosen.currency}"
        )
        confirm = _format_propose(product=chosen, options=options)

        if self.gateway is None:
            return ProposePurchaseResult(
                ok=False,
                parsed=parsed,
                approval_id=None,
                task_id=task.id,
                tier=tier.value,
                reason="gateway_required_for_hard_approve",
                confirm_body=confirm,
                price=chosen.price,
                currency=chosen.currency,
                merchant=chosen.merchant,
                sku=chosen.sku,
                options=options,
            )

        buy_before = self.gateway.commerce.buy_count
        gw_result = self.gateway.propose(
            "buy",
            summary,
            payload,
            estimated_cost=float(chosen.price),
            source_channel=source_channel,
            source_utterance=source_utterance or parsed.raw,
        )

        if not gw_result.ok or not gw_result.approval_id:
            return ProposePurchaseResult(
                ok=False,
                parsed=parsed,
                approval_id=gw_result.approval_id,
                task_id=task.id,
                tier=gw_result.tier or tier.value,
                reason=gw_result.reason,
                confirm_body="",
                price=chosen.price,
                currency=chosen.currency,
                merchant=chosen.merchant,
                sku=chosen.sku,
                options=options,
                gateway_result=gw_result,
                executed=gw_result.executed,
                buy_count_at_propose=self.gateway.commerce.buy_count,
            )

        leaked = gw_result.executed or self.gateway.commerce.buy_count != buy_before
        if leaked:
            return ProposePurchaseResult(
                ok=False,
                parsed=parsed,
                approval_id=gw_result.approval_id,
                task_id=task.id,
                tier=gw_result.tier or tier.value,
                reason="hard_approve_leaked_buy",
                confirm_body="",
                price=chosen.price,
                currency=chosen.currency,
                merchant=chosen.merchant,
                sku=chosen.sku,
                options=options,
                gateway_result=gw_result,
                executed=True,
                buy_count_at_propose=self.gateway.commerce.buy_count,
            )

        self.store.set_approval(task.id, gw_result.approval_id, at=self.clock.now())

        self.catcher.send(
            "whatsapp",
            recipient or "owner",
            confirm,
            ts=self.clock.now(),
            kind="shopping_propose",
            approval_id=gw_result.approval_id,
            purchase_task_id=task.id,
            price=chosen.price,
            currency=chosen.currency,
            merchant=chosen.merchant,
            sku=chosen.sku,
        )

        return ProposePurchaseResult(
            ok=True,
            parsed=parsed,
            approval_id=gw_result.approval_id,
            task_id=task.id,
            tier=gw_result.tier or tier.value,
            reason="pending_hard_approve",
            confirm_body=confirm,
            price=chosen.price,
            currency=chosen.currency,
            merchant=chosen.merchant,
            sku=chosen.sku,
            options=options,
            gateway_result=gw_result,
            executed=False,
            buy_count_at_propose=self.gateway.commerce.buy_count,
        )

    def mark_denied_for_approval(self, approval_id: str) -> Optional[PurchaseTask]:
        for task in self.store.list_all():
            if task.approval_id == approval_id:
                return self.store.mark_denied(task.id, at=self.clock.now())
        return None


__all__ = [
    "ShoppingService",
    "ProposePurchaseResult",
    "looks_like_shopping",
    "parse_shopping",
]
