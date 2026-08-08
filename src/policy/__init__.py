"""Policy helpers used by Gateway skills and INV-* contract tests.

Heavy modules (action_gateway) are imported by callers directly to avoid
circular imports with harness adapters.
"""

from .ingress import evaluate_ingress, is_sender_allowed

__all__ = [
    "evaluate_ingress",
    "is_sender_allowed",
]
