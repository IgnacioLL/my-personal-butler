"""Self-modification capability — propose diff → hard approve → apply.

Import service from capabilities.selfmod.service when wiring harness clocks.
"""

from capabilities.selfmod.allowlist import (
    AllowlistConfig,
    is_policy_path,
    path_allowed,
)
from capabilities.selfmod.parse import (
    EXPECTED_E2E08_UTTERANCE,
    ParsedSelfModRequest,
    looks_like_self_mod,
    parse_self_mod,
)
from capabilities.selfmod.secrets import (
    SelfModSecretsError,
    scan_diff_for_secrets,
    validate_patch_no_secrets,
)

__all__ = [
    "AllowlistConfig",
    "EXPECTED_E2E08_UTTERANCE",
    "ParsedSelfModRequest",
    "SelfModSecretsError",
    "is_policy_path",
    "looks_like_self_mod",
    "parse_self_mod",
    "path_allowed",
    "scan_diff_for_secrets",
    "validate_patch_no_secrets",
]
