"""Harness chat-model stubs — deterministic completions, no network."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from intelligence.models.roles import ModelRole


@dataclass(frozen=True)
class StubCompletion:
    """Synthetic model response for contract tests (assert structure, not prose)."""

    model: ModelRole
    text: str
    tokens_in: int
    tokens_out: int
    stub: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.value,
            "text": self.text,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "stub": self.stub,
        }


@dataclass
class ChatModelStub:
    """Per-role stub that records calls without contacting live Luna/Terra/Sol."""

    role: ModelRole
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(self, prompt: str, *, context_tokens: int = 0) -> StubCompletion:
        tokens_in = max(1, len(prompt.split()) + context_tokens)
        tokens_out = min(64, max(8, tokens_in // 4))
        text = f"[stub:{self.role.value}] len={len(prompt)}"
        self.calls.append(
            {
                "role": self.role.value,
                "prompt_len": len(prompt),
                "context_tokens": context_tokens,
            }
        )
        return StubCompletion(
            model=self.role,
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def snapshot(self) -> dict[str, Any]:
        return {"role": self.role.value, "call_count": len(self.calls)}


class ModelStubRegistry:
    """Registry of chat stubs keyed by ModelRole."""

    def __init__(self) -> None:
        self._stubs: dict[ModelRole, ChatModelStub] = {
            role: ChatModelStub(role=role) for role in ModelRole
        }

    def for_role(self, role: ModelRole) -> ChatModelStub:
        return self._stubs[role]

    def complete_as(self, role: ModelRole, prompt: str, **kwargs: Any) -> StubCompletion:
        return self.for_role(role).complete(prompt, **kwargs)

    def snapshot(self) -> dict[str, Any]:
        return {role.value: stub.snapshot() for role, stub in self._stubs.items()}
