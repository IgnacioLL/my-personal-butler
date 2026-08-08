"""Model role identifiers for the Luna / Terra / Sol routing ladder."""

from __future__ import annotations

from enum import Enum


class ModelRole(str, Enum):
    """Chat / planning model tiers (harness stubs — no live providers in CI)."""

    LUNA = "luna"
    TERRA = "terra"
    SOL = "sol"


class IntentKind(str, Enum):
    """Deterministic intent classes used by the router (not NLU — fixture-driven)."""

    REMINDER = "reminder"
    TODO = "todo"
    FAQ = "faq"
    CALENDAR_READ = "calendar_read"
    DIET_SWAP = "diet_swap"
    APPROVAL_SUMMARY = "approval_summary"
    DOC_TWEAK = "doc_tweak"
    PLANNING = "planning"
    BOOKING = "booking"
    SELF_MOD = "self_mod"
    GENERAL = "general"
