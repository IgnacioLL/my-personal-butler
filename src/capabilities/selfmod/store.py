"""In-memory self-mod proposal store for harness assertions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    DENIED = "denied"
    BLOCKED = "blocked"
    REJECTED = "rejected"


@dataclass
class SelfModProposal:
    id: str
    intent: str
    summary: str
    files_touched: list[str]
    file_contents: dict[str, str]  # new contents after apply
    diff_text: str
    diff_summary: str
    rollback_ref: str
    branch: str
    action_type: str  # self_mod_apply | policy_change
    subtype: Optional[str]
    status: ProposalStatus
    created_at: datetime
    approval_id: Optional[str] = None
    apply_id: Optional[str] = None
    commit_sha: Optional[str] = None
    risk_notes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        return data


class ProposalStore:
    def __init__(self) -> None:
        self._items: dict[str, SelfModProposal] = {}

    def add(self, proposal: SelfModProposal) -> SelfModProposal:
        self._items[proposal.id] = proposal
        return proposal

    def get(self, proposal_id: str) -> Optional[SelfModProposal]:
        return self._items.get(proposal_id)

    def by_approval(self, approval_id: str) -> Optional[SelfModProposal]:
        for item in self._items.values():
            if item.approval_id == approval_id:
                return item
        return None

    def list(self) -> list[SelfModProposal]:
        return list(self._items.values())

    def mark_applied(
        self,
        proposal_id: str,
        *,
        apply_id: str,
        commit_sha: str,
        at: datetime | None = None,
    ) -> SelfModProposal:
        item = self._items[proposal_id]
        item.status = ProposalStatus.APPLIED
        item.apply_id = apply_id
        item.commit_sha = commit_sha
        if at is not None:
            item.meta["applied_at"] = at.isoformat()
        return item

    def mark_denied(self, proposal_id: str) -> SelfModProposal:
        item = self._items[proposal_id]
        item.status = ProposalStatus.DENIED
        return item

    def mark_blocked(self, proposal_id: str, reason: str) -> SelfModProposal:
        item = self._items[proposal_id]
        item.status = ProposalStatus.BLOCKED
        item.meta["block_reason"] = reason
        return item

    def new_id(self) -> str:
        return str(uuid4())
