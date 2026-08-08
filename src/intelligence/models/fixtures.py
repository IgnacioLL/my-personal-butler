"""Load routing-intents fixture pack for router contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_fixture_path() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "fixtures" / "models" / "routing-intents.json"
    )


def load_routing_fixture(path: Path | None = None) -> dict[str, Any]:
    fixture_path = path or default_fixture_path()
    return json.loads(fixture_path.read_text(encoding="utf-8"))
