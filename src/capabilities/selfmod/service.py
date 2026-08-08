"""Self-mod service — propose allowlisted diffs; apply only after hard Accept."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from capabilities.selfmod.allowlist import (
    AllowlistConfig,
    assert_paths_allowed,
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
    validate_patch_no_secrets,
)
from capabilities.selfmod.store import (
    ProposalStatus,
    ProposalStore,
    SelfModProposal,
)
from capabilities.selfmod.workspace import FixtureWorkspace
from harness.clock import FakeClock
from harness.outbound import OutboundMessageCatcher
from policy.action_gateway import ActionGateway, ProposeResult
from policy.approvals import ApprovalTier, tier_for

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ALLOWLIST = ROOT / "fixtures" / "selfmod" / "allowlist.json"
DEFAULT_WORKSPACE = ROOT / "fixtures" / "selfmod" / "sample-workspace"
DEFAULT_CONFIG = ROOT / "config" / "selfmod.harness.json"


@dataclass
class ProposeSelfModResult:
    ok: bool
    reason: str
    approval_id: Optional[str] = None
    proposal_id: Optional[str] = None
    tier: str = ApprovalTier.HARD_APPROVE.value
    action_type: str = "self_mod_apply"
    subtype: Optional[str] = None
    files_touched: list[str] = field(default_factory=list)
    diff_summary: Optional[str] = None
    diff_text: Optional[str] = None
    rollback_ref: Optional[str] = None
    branch: Optional[str] = None
    apply_available: bool = False
    tree_clean: bool = True
    gateway_result: Optional[ProposeResult] = None
    parsed: Optional[ParsedSelfModRequest] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "approval_id": self.approval_id,
            "proposal_id": self.proposal_id,
            "tier": self.tier,
            "action_type": self.action_type,
            "subtype": self.subtype,
            "files_touched": list(self.files_touched),
            "diff_summary": self.diff_summary,
            "diff_text": self.diff_text,
            "rollback_ref": self.rollback_ref,
            "branch": self.branch,
            "apply_available": self.apply_available,
            "tree_clean": self.tree_clean,
            "parsed": (
                {
                    "kind": self.parsed.kind,
                    "raw": self.parsed.raw,
                    "no_calls_after": self.parsed.no_calls_after,
                    "intent_summary": self.parsed.intent_summary,
                }
                if self.parsed
                else None
            ),
        }


def _unified_hunk(path: str, old: str, new: str) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    parts = [
        f"--- a/{path}",
        f"+++ b/{path}",
        f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@",
    ]
    for line in old_lines:
        parts.append(f"-{line}")
    for line in new_lines:
        parts.append(f"+{line}")
    return "\n".join(parts)


def build_quiet_hours_patch(
    workspace: FixtureWorkspace,
    *,
    no_calls_after: str = "22:00",
) -> tuple[dict[str, str], str, str]:
    """Return (new_contents_by_path, diff_text, diff_summary) for quiet hours."""
    reminders_path = "skills/reminders.md"
    agent_path = "config/agent.json"
    old_reminders = workspace.read(reminders_path)
    old_agent = workspace.read(agent_path)

    new_reminders = (
        "# Reminders skill\n"
        "\n"
        "Policies for proactive reminders and outbound calls.\n"
        "\n"
        "## Quiet hours\n"
        "\n"
        "quiet_hours:\n"
        "  enabled: true\n"
        f'  start: "{no_calls_after}"\n'
        '  end: "08:00"\n'
        "  block_calls: true\n"
        "\n"
        "## Notes\n"
        "\n"
        "- Soft confirm for calendar writes\n"
        "- Hard approve for money and self-mod\n"
    )
    agent_data = json.loads(old_agent)
    agent_data["quiet_hours"] = {
        "enabled": True,
        "no_calls_after": no_calls_after,
    }
    new_agent = json.dumps(agent_data, indent=2, sort_keys=True) + "\n"

    files = {reminders_path: new_reminders, agent_path: new_agent}
    diff_text = "\n".join(
        [
            _unified_hunk(reminders_path, old_reminders, new_reminders),
            _unified_hunk(agent_path, old_agent, new_agent),
        ]
    )
    summary = (
        f"Enable quiet hours — block outbound calls after {no_calls_after} "
        f"({reminders_path}, {agent_path})"
    )
    return files, diff_text, summary


def build_policy_change_patch(
    workspace: FixtureWorkspace,
    *,
    new_cap: float = 100.0,
) -> tuple[dict[str, str], str, str]:
    path = "src/policy/approvals_stub.py"
    old = workspace.read(path)
    new = old.replace(
        "DEFAULT_SPEND_CAP = 50.0",
        f"DEFAULT_SPEND_CAP = {new_cap}",
    )
    if new == old:
        new = old.rstrip() + f"\n# policy-change: DEFAULT_SPEND_CAP -> {new_cap}\n"
    files = {path: new}
    diff_text = _unified_hunk(path, old, new)
    summary = f"Policy change: raise DEFAULT_SPEND_CAP to {new_cap}"
    return files, diff_text, summary


class SelfModService:
    """Propose patches on a fixture workspace; apply only via gateway Accept."""

    def __init__(
        self,
        clock: FakeClock,
        catcher: OutboundMessageCatcher,
        *,
        gateway: ActionGateway | None = None,
        workspace: FixtureWorkspace | None = None,
        allowlist: AllowlistConfig | None = None,
        store: ProposalStore | None = None,
        recipient: str = "",
        workspace_fixture: Path | str | None = None,
        allowlist_path: Path | str | None = None,
        work_dir: Path | str | None = None,
    ) -> None:
        self.clock = clock
        self.catcher = catcher
        self.gateway = gateway
        self.store = store if store is not None else ProposalStore()
        self.recipient = recipient
        self._work_dir = Path(work_dir) if work_dir is not None else None
        self._tmp: tempfile.TemporaryDirectory[str] | None = None

        if allowlist is not None:
            self.allowlist = allowlist
        else:
            alist = Path(allowlist_path) if allowlist_path else DEFAULT_ALLOWLIST
            self.allowlist = (
                AllowlistConfig.from_file(alist)
                if alist.is_file()
                else AllowlistConfig()
            )

        if workspace is not None:
            self.workspace = workspace
        else:
            fixture = (
                Path(workspace_fixture) if workspace_fixture else DEFAULT_WORKSPACE
            )
            if self._work_dir is None:
                self._tmp = tempfile.TemporaryDirectory(prefix="selfmod-ws-")
                dest = Path(self._tmp.name) / "workspace"
            else:
                dest = Path(self._work_dir)
            self.workspace = FixtureWorkspace.from_fixture(fixture, dest=dest)

        if self.gateway is not None:
            self.gateway.attach_selfmod(self)

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    @property
    def apply_tools_available(self) -> bool:
        """Apply/write tools are unavailable until Accept (and not while frozen)."""
        if self.gateway is not None and self.gateway.kill.self_mod_frozen:
            return False
        return False  # never ambiently available — only via gateway.execute

    def tools_for_session(self) -> dict[str, bool]:
        """Propose/read remain available under freeze; apply/write stay gated."""
        frozen = bool(
            self.gateway is not None and self.gateway.kill.self_mod_frozen
        )
        return {
            "source_read": True,
            "self_mod_propose": True,
            # Apply tools are never ambiently available — only gateway.execute
            # after Accept. Freeze additionally refuses execute (INV-SELF-002).
            "self_mod_apply": False,
            "policy_change": False,
            "freeze_self_mod": frozen,
        }

    def read_source(self, rel_path: str) -> str:
        if not path_allowed(rel_path, self.allowlist):
            raise ValueError(f"outside_allowlist:{rel_path}")
        return self.workspace.read(rel_path)

    def propose_from_utterance(
        self,
        utterance: str,
        *,
        recipient: str | None = None,
        source_channel: str = "whatsapp",
    ) -> ProposeSelfModResult:
        try:
            parsed = parse_self_mod(utterance)
        except ValueError as exc:
            return ProposeSelfModResult(
                ok=False,
                reason=f"parse_error:{exc}",
                tree_clean=self.workspace.working_tree_clean(),
            )
        return self.propose_for_request(
            parsed,
            recipient=recipient if recipient is not None else self.recipient,
            source_channel=source_channel,
            source_utterance=utterance,
        )

    def propose_for_request(
        self,
        parsed: ParsedSelfModRequest,
        *,
        recipient: str = "",
        source_channel: str = "whatsapp",
        source_utterance: str | None = None,
    ) -> ProposeSelfModResult:
        if parsed.kind == "policy_change":
            files, diff_text, summary = build_policy_change_patch(self.workspace)
            action_type = "policy_change"
            subtype = "policy-change"
            risk = [
                "Touches approval/safety fixture code",
                "Requires policy-change subtype (louder approval)",
            ]
        else:
            after = parsed.no_calls_after or "22:00"
            files, diff_text, summary = build_quiet_hours_patch(
                self.workspace, no_calls_after=after
            )
            action_type = "self_mod_apply"
            subtype = None
            risk = [
                "Affects proactive call escalation only",
                "No approval-matrix change",
            ]

        # Policy-path heuristic override (even if intent was quiet-hours).
        if any(is_policy_path(p, self.allowlist) for p in files):
            action_type = "policy_change"
            subtype = "policy-change"
            if "Touches approval/safety fixture code" not in risk:
                risk.insert(0, "Touches approval/safety fixture code")

        return self.propose_patch(
            intent=parsed.intent_summary or parsed.raw,
            summary=summary,
            files=files,
            diff_text=diff_text,
            action_type=action_type,
            subtype=subtype,
            risk_notes=risk,
            recipient=recipient,
            source_channel=source_channel,
            source_utterance=source_utterance or parsed.raw,
            parsed=parsed,
        )

    def propose_patch(
        self,
        *,
        intent: str,
        summary: str,
        files: dict[str, str],
        diff_text: str,
        action_type: str = "self_mod_apply",
        subtype: str | None = None,
        risk_notes: list[str] | None = None,
        recipient: str = "",
        source_channel: str = "whatsapp",
        source_utterance: str | None = None,
        parsed: ParsedSelfModRequest | None = None,
    ) -> ProposeSelfModResult:
        paths = sorted(files.keys())
        tree_clean = self.workspace.working_tree_clean()

        # INV-SELF-001: outside allowlist fail closed (no approval created).
        try:
            assert_paths_allowed(paths, self.allowlist)
        except ValueError as exc:
            return ProposeSelfModResult(
                ok=False,
                reason=str(exc),
                files_touched=paths,
                tree_clean=tree_clean,
                apply_available=False,
                parsed=parsed,
            )

        # INV-SELF-004: secrets rejected from proposed commits.
        try:
            validate_patch_no_secrets({"files": files, "diff": diff_text})
        except SelfModSecretsError as exc:
            return ProposeSelfModResult(
                ok=False,
                reason=f"secrets_rejected:{exc}",
                files_touched=paths,
                diff_text=diff_text,
                tree_clean=tree_clean,
                apply_available=False,
                parsed=parsed,
            )

        line_count = diff_text.count("\n") + (1 if diff_text else 0)
        if line_count > self.allowlist.diff_ceiling_lines:
            return ProposeSelfModResult(
                ok=False,
                reason=f"diff_ceiling:{line_count}>{self.allowlist.diff_ceiling_lines}",
                files_touched=paths,
                diff_text=diff_text,
                tree_clean=tree_clean,
                apply_available=False,
                parsed=parsed,
            )

        if any(is_policy_path(p, self.allowlist) for p in paths):
            action_type = "policy_change"
            subtype = "policy-change"

        tier = tier_for(action_type)
        if tier != ApprovalTier.HARD_APPROVE:
            return ProposeSelfModResult(
                ok=False,
                reason=f"expected_hard_approve_got_{tier.value}",
                tier=tier.value,
                action_type=action_type,
                subtype=subtype,
                files_touched=paths,
                tree_clean=tree_clean,
                parsed=parsed,
            )

        rollback = self.workspace.rollback_ref()
        branch = f"{self.allowlist.branch_prefix}quiet-hours"
        if action_type == "policy_change":
            branch = f"{self.allowlist.branch_prefix}policy-change"
        proposal_id = self.store.new_id()

        proposal = SelfModProposal(
            id=proposal_id,
            intent=intent,
            summary=summary,
            files_touched=paths,
            file_contents=dict(files),
            diff_text=diff_text,
            diff_summary=summary,
            rollback_ref=rollback,
            branch=branch,
            action_type=action_type,
            subtype=subtype,
            status=ProposalStatus.PROPOSED,
            created_at=self.clock.now(),
            risk_notes=list(risk_notes or []),
            meta={"recipient": recipient},
        )
        self.store.add(proposal)

        # Working tree must stay unchanged until Accept.
        if not self.workspace.working_tree_clean():
            return ProposeSelfModResult(
                ok=False,
                reason="workspace_dirty_before_propose",
                proposal_id=proposal_id,
                tree_clean=False,
                apply_available=False,
                parsed=parsed,
            )

        payload = {
            "proposal_id": proposal_id,
            "files": paths,
            "file_contents": dict(files),
            "diff": diff_text,
            "branch": branch,
            "rollback_ref": rollback,
            "intent": intent,
            "risk_notes": list(risk_notes or []),
            "recipient": recipient or self.recipient,
        }

        if self.gateway is None:
            return ProposeSelfModResult(
                ok=False,
                reason="gateway_required",
                proposal_id=proposal_id,
                action_type=action_type,
                subtype=subtype,
                files_touched=paths,
                diff_summary=summary,
                diff_text=diff_text,
                rollback_ref=rollback,
                branch=branch,
                tree_clean=True,
                apply_available=False,
                parsed=parsed,
            )

        gw_result = self.gateway.propose(
            action_type,
            summary,
            payload,
            diff_summary=summary,
            files_touched=paths,
            rollback_ref=rollback,
            source_channel=source_channel,
            source_utterance=source_utterance,
            subtype=subtype,
        )
        if not gw_result.ok or not gw_result.approval_id:
            return ProposeSelfModResult(
                ok=False,
                reason=gw_result.reason,
                proposal_id=proposal_id,
                tier=gw_result.tier or tier.value,
                action_type=action_type,
                subtype=subtype,
                files_touched=paths,
                diff_summary=summary,
                diff_text=diff_text,
                rollback_ref=rollback,
                branch=branch,
                tree_clean=self.workspace.working_tree_clean(),
                apply_available=False,
                gateway_result=gw_result,
                parsed=parsed,
            )

        proposal.approval_id = gw_result.approval_id

        body = (
            f"Self-mod proposal: {summary}\n"
            f"Files: {', '.join(paths)}\n"
            f"Branch: {branch}\n"
            f"Rollback: {rollback}\n"
            f"Hard approve required before apply."
        )
        self.catcher.send(
            "whatsapp",
            recipient or self.recipient or "owner",
            body,
            ts=self.clock.now(),
            kind="selfmod_propose",
            approval_id=gw_result.approval_id,
            proposal_id=proposal_id,
            files=paths,
            subtype=subtype,
        )

        return ProposeSelfModResult(
            ok=True,
            reason="pending_approval",
            approval_id=gw_result.approval_id,
            proposal_id=proposal_id,
            tier=tier.value,
            action_type=action_type,
            subtype=subtype,
            files_touched=paths,
            diff_summary=summary,
            diff_text=diff_text,
            rollback_ref=rollback,
            branch=branch,
            apply_available=False,
            tree_clean=self.workspace.working_tree_clean(),
            gateway_result=gw_result,
            parsed=parsed,
        )

    def apply_payload(
        self,
        payload: dict[str, Any],
        *,
        approval_id: str | None = None,
        action_type: str = "self_mod_apply",
    ) -> dict[str, Any]:
        """Apply after Accept — called only from ActionGateway._run_adapter."""
        if self.gateway is not None and self.gateway.kill.self_mod_frozen:
            raise RuntimeError("freeze_self_mod")

        proposal_id = payload.get("proposal_id")
        proposal = self.store.get(str(proposal_id)) if proposal_id else None
        files = dict(payload.get("file_contents") or {})
        if proposal is not None and not files:
            files = dict(proposal.file_contents)
        if not files:
            raise ValueError("missing_file_contents")

        paths = sorted(files.keys())
        assert_paths_allowed(paths, self.allowlist)
        validate_patch_no_secrets({"files": files, "diff": payload.get("diff", "")})

        branch = str(
            payload.get("branch")
            or (proposal.branch if proposal else f"{self.allowlist.branch_prefix}patch")
        )
        diff_text = str(
            payload.get("diff") or (proposal.diff_text if proposal else "")
        )
        applied = self.workspace.apply_files(
            files,
            branch=branch,
            approval_id=approval_id,
            diff_text=diff_text,
        )

        if proposal is not None:
            self.store.mark_applied(
                proposal.id,
                apply_id=applied.apply_id,
                commit_sha=applied.commit_sha,
                at=self.clock.now(),
            )

        # Keep stub adapter counters in sync when gateway is attached.
        if self.gateway is not None:
            if action_type == "policy_change":
                self.gateway.selfmod.policy_change_count += 1
            else:
                self.gateway.selfmod.apply_count += 1
            self.gateway.selfmod.applied.append(
                {
                    "apply_id": applied.apply_id,
                    "approval_id": approval_id,
                    **applied.to_dict(),
                }
            )

        if self.catcher is not None:
            self.catcher.send(
                "whatsapp",
                str(payload.get("recipient") or self.recipient or "owner"),
                (
                    f"Self-mod applied on {branch} "
                    f"(commit {applied.commit_sha}, rollback {applied.rollback_ref})."
                ),
                ts=self.clock.now(),
                kind="selfmod_applied",
                approval_id=approval_id,
                commit_sha=applied.commit_sha,
                rollback_ref=applied.rollback_ref,
                branch=branch,
            )

        return {
            "apply_id": applied.apply_id,
            "approval_id": approval_id,
            "branch": applied.branch,
            "rollback_ref": applied.rollback_ref,
            "commit_sha": applied.commit_sha,
            "files_touched": applied.files_touched,
            "action_type": action_type,
            "tree_clean": self.workspace.working_tree_clean(),
        }

    def mark_denied(self, approval_id: str) -> None:
        proposal = self.store.by_approval(approval_id)
        if proposal is not None:
            self.store.mark_denied(proposal.id)

    def mark_blocked(self, approval_id: str, reason: str) -> None:
        proposal = self.store.by_approval(approval_id)
        if proposal is not None:
            self.store.mark_blocked(proposal.id, reason)


# Re-export for tests / CI
__all__ = [
    "EXPECTED_E2E08_UTTERANCE",
    "ProposeSelfModResult",
    "SelfModService",
    "build_policy_change_patch",
    "build_quiet_hours_patch",
    "looks_like_self_mod",
]
