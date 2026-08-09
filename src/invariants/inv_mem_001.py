"""INV-MEM-001 — secret-like patterns must not be written to memory files."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from intelligence.memory.secrets import MemorySecretsError
from intelligence.memory.store import MemoryStore

INV_ID = "INV-MEM-001"
DESCRIPTION = "Secrets patterns are rejected from memory profile and episodic writes"


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    samples = [
        ("profile", "preferences", "note", "api_key=sk-abcdefghijklmnopqrstuvwxyz12345"),
        ("profile", "identity", "token", "password: hunter2"),
        ("episode", None, None, "Bearer ghp_abcdefghijklmnopqrstuvwxyz1234567890"),
        ("episode", None, None, "-----BEGIN RSA PRIVATE KEY-----"),
    ]

    with tempfile.TemporaryDirectory(prefix="inv-mem-001-") as tmp:
        root = Path(tmp) / "mem"
        store = MemoryStore.seed(root)

        for kind, section, key, payload in samples:
            try:
                if kind == "profile":
                    store.remember(section, key, payload)  # type: ignore[arg-type]
                    failures.append(f"{payload[:24]}… should be rejected (profile)")
                else:
                    store.append_episode(payload)
                    failures.append(f"{payload[:24]}… should be rejected (episode)")
            except MemorySecretsError:
                pass
            except Exception as exc:  # noqa: BLE001
                failures.append(f"unexpected error for {kind}: {exc}")

        # Disk must not contain raw secret substrings.
        profile_text = store.profile_path.read_text(encoding="utf-8")
        episodes_text = store.episodes_path.read_text(encoding="utf-8")
        for needle in ("sk-abcdefghijklmnopqrst", "hunter2", "PRIVATE KEY", "ghp_"):
            if needle in profile_text or needle in episodes_text:
                failures.append(f"secret substring leaked to disk: {needle!r}")

        # Positive control: benign remember persists.
        store.remember("preferences", "food_likes", ["olive oil"], explicit=True)
        reopened = MemoryStore.open(root)
        hot = reopened.load_hot_profile()
        likes = hot.get("preferences", {}).get("food_likes", [])
        if "olive oil" not in likes:
            failures.append(f"benign remember failed: {likes!r}")

        # JSON parse sanity.
        try:
            json.loads(store.profile_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"profile JSON invalid: {exc}")

    if failures:
        return {"id": INV_ID, "result": "FAIL", "detail": "; ".join(failures)}
    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": "secret patterns rejected; benign facts persist; disk clean",
    }
