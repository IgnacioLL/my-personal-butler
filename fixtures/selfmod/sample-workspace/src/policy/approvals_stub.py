"""Fixture stand-in for approval-matrix / safety code (policy-change subtype).

Not the real runtime module — only used inside fixtures/selfmod sample workspace.
"""

APPROVAL_TIERS = {
    "buy": "hard_approve",
    "self_mod_apply": "hard_approve",
}

# Spend cap placeholder — policy-change tests may patch this value.
DEFAULT_SPEND_CAP = 50.0
