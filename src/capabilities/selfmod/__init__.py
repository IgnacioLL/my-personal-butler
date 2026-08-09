"""Self-modification capability — propose diff → hard approve → apply.

Import service from capabilities.selfmod.service when wiring harness clocks.
Production allowlist/skill: capabilities.selfmod.production (PROD-09).
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
from capabilities.selfmod.production import (
    ProductionSelfModConfig,
    load_production_allowlist,
    load_production_config,
    production_paths_smoke,
    production_skill_present,
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
    "ProductionSelfModConfig",
    "SelfModSecretsError",
    "is_policy_path",
    "load_production_allowlist",
    "load_production_config",
    "looks_like_self_mod",
    "parse_self_mod",
    "path_allowed",
    "production_paths_smoke",
    "production_skill_present",
    "scan_diff_for_secrets",
    "validate_patch_no_secrets",
]
