"""Dry-run merchant catalog — deterministic product search; no live network."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class MerchantProduct:
    sku: str
    name: str
    brand: str
    size: str
    price: float
    currency: str
    merchant: str
    aliases: tuple[str, ...] = ()
    usual: bool = False
    item_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "size": self.size,
            "price": self.price,
            "currency": self.currency,
            "merchant": self.merchant,
            "aliases": list(self.aliases),
            "usual": self.usual,
            "item_key": self.item_key,
        }


@dataclass
class DryRunMerchant:
    """In-memory merchant double: search only; purchase via commerce.buy dry-run.

    Never charges a real card — StubCommerceAdapter.buy records dry-run receipts.
    """

    merchant: str = "StubMart"
    merchant_url: str = "https://stub.merchant.test/stubmart"
    currency: str = "EUR"
    products: list[MerchantProduct] = field(default_factory=list)
    search_count: int = 0

    @classmethod
    def from_fixture(cls, path: Path | str) -> "DryRunMerchant":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        merchant = str(data.get("merchant") or "StubMart")
        currency = str(data.get("currency") or "EUR")
        products: list[MerchantProduct] = []
        for raw in data.get("products") or []:
            products.append(
                MerchantProduct(
                    sku=str(raw.get("sku") or f"sku-{len(products)+1}"),
                    name=str(raw.get("name") or ""),
                    brand=str(raw.get("brand") or ""),
                    size=str(raw.get("size") or ""),
                    price=float(raw.get("price") or 0),
                    currency=str(raw.get("currency") or currency),
                    merchant=str(raw.get("merchant") or merchant),
                    aliases=tuple(str(a) for a in (raw.get("aliases") or [])),
                    usual=bool(raw.get("usual")),
                    item_key=str(raw.get("item_key") or ""),
                )
            )
        return cls(
            merchant=merchant,
            merchant_url=str(data.get("merchant_url") or ""),
            currency=currency,
            products=products,
        )

    def search(
        self,
        *,
        query: str = "",
        item_key: str | None = None,
        prefer_usual: bool = True,
        limit: int = 3,
    ) -> list[MerchantProduct]:
        """Return matching catalog rows (read-only). Prefer usual rebuy when set."""
        self.search_count += 1
        q = (query or "").strip().lower()
        key = (item_key or "").strip().lower()
        scored: list[tuple[int, MerchantProduct]] = []
        for product in self.products:
            score = 0
            if key and product.item_key.lower() == key:
                score += 10
            if prefer_usual and product.usual:
                score += 5
            hay = " ".join(
                [
                    product.name,
                    product.brand,
                    product.size,
                    product.item_key,
                    " ".join(product.aliases),
                ]
            ).lower()
            if q and q in hay:
                score += 3
            if q:
                for token in q.split():
                    if token and token in hay:
                        score += 1
            if score > 0:
                scored.append((score, product))
        scored.sort(key=lambda pair: (-pair[0], pair[1].price))
        return [p for _, p in scored[:limit]]

    def find_usual(self, item_key: str) -> Optional[MerchantProduct]:
        key = (item_key or "").strip().lower()
        for product in self.products:
            if product.usual and product.item_key.lower() == key:
                return product
        for product in self.products:
            if product.usual:
                return product
        return None

    def merchant_card(self) -> dict[str, Any]:
        return {
            "merchant": self.merchant,
            "merchant_url": self.merchant_url,
            "currency": self.currency,
            "product_count": len(self.products),
        }

    def reset_counters(self) -> None:
        self.search_count = 0
