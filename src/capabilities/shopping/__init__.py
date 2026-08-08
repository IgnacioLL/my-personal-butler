"""Shopping capability — dry-run merchant behind hard approve + spend caps.

Import service from capabilities.shopping.service directly when needed alongside
harness clocks to avoid circular package init.
"""

from capabilities.shopping.merchant import DryRunMerchant, MerchantProduct
from capabilities.shopping.parse import (
    EXPECTED_E2E07_UTTERANCE,
    ParsedShoppingRequest,
    looks_like_shopping,
    parse_shopping,
)
from capabilities.shopping.store import PurchaseStatus, PurchaseStore, PurchaseTask

__all__ = [
    "EXPECTED_E2E07_UTTERANCE",
    "DryRunMerchant",
    "MerchantProduct",
    "ParsedShoppingRequest",
    "PurchaseStatus",
    "PurchaseStore",
    "PurchaseTask",
    "looks_like_shopping",
    "parse_shopping",
]
