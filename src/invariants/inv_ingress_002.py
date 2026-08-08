"""INV-INGRESS-002 — group messages ignored while groups are disabled.

Adversarial cases: allowlisted member in group, group_id without is_group flag,
group JID as sender, broadcast lists, mixed DM then group (DM may run; group must not).
"""

from __future__ import annotations

from typing import Any

from harness.ingress_sim import IngressSimulator
from harness.outbound import OutboundMessageCatcher
from harness.whatsapp_transport import InboundWhatsAppMessage, MockWhatsAppTransport

INV_ID = "INV-INGRESS-002"
DESCRIPTION = "Group messages are ignored while groups are disabled"

OWNER = "+15550001111"


def _fail(detail: str) -> dict[str, Any]:
    return {"id": INV_ID, "result": "FAIL", "detail": detail}


def _group_must_be_ignored(
    transport: MockWhatsAppTransport,
    *,
    label: str,
    allowed: bool,
    reason: str,
    baseline_tools: int,
    baseline_outbound: int,
) -> str | None:
    if allowed:
        return f"{label}: group allowed while groups disabled (reason={reason})"
    if transport.counters.tool_calls != baseline_tools:
        return (
            f"{label}: tool_calls changed "
            f"{baseline_tools}→{transport.counters.tool_calls} reason={reason}"
        )
    if transport.counters.outbound_sends != baseline_outbound:
        return (
            f"{label}: outbound changed "
            f"{baseline_outbound}→{transport.counters.outbound_sends} reason={reason}"
        )
    if transport.counters.hard_action_attempts:
        return f"{label}: hard_action_attempts={transport.counters.hard_action_attempts}"
    return None


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    allowlist = list(ctx.get("allowlist") or [OWNER])
    broken = bool(ctx.get("broken_allow_all", False))
    failures: list[str] = []

    catcher = OutboundMessageCatcher()
    transport = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=catcher,
        groups_enabled=False,
        broken_allow_all=broken,
    )

    cases: list[tuple[str, InboundWhatsAppMessage]] = [
        (
            "allowlisted_in_group",
            InboundWhatsAppMessage(
                sender=allowlist[0],
                body="group noise",
                is_group=True,
                group_id="120363-test@g.us",
            ),
        ),
        (
            "group_id_without_flag",
            InboundWhatsAppMessage(
                sender=allowlist[0],
                body="sneaky group_id",
                is_group=False,
                group_id="120363-sneaky@g.us",
            ),
        ),
        (
            "group_jid_sender",
            InboundWhatsAppMessage(
                sender="12036399@g.us",
                body="jid as sender",
                is_group=False,
            ),
        ),
        (
            "broadcast_sender",
            InboundWhatsAppMessage(
                sender="status@broadcast",
                body="broadcast",
                is_group=False,
            ),
        ),
        (
            "stranger_in_group",
            InboundWhatsAppMessage(
                sender="+19999999999",
                body="stranger group",
                is_group=True,
                group_id="g-1",
            ),
        ),
        (
            "group_prefix_meta",
            InboundWhatsAppMessage(
                sender=allowlist[0],
                body="group:meta",
                is_group=False,
                group_id="group:internal",
            ),
        ),
    ]

    for label, msg in cases:
        before_tools = transport.counters.tool_calls
        before_out = transport.counters.outbound_sends
        result = transport.inject(msg)
        if broken:
            # Fail-closed proof: broken_allow_all lets traffic through — INV must FAIL.
            if result.allowed and (
                transport.counters.tool_calls > before_tools
                or transport.counters.outbound_sends > before_out
            ):
                return _fail(
                    f"group message produced effects while groups disabled "
                    f"(allowed={result.allowed}, tools={transport.tool_call_log!r}, "
                    f"outbound={catcher.count()}, reason={result.reason})"
                )
            if result.allowed:
                return _fail(
                    f"group message produced effects while groups disabled "
                    f"(allowed={result.allowed}, tools={result.tool_calls!r}, "
                    f"outbound={result.outbound_count}, reason={result.reason})"
                )
            continue

        err = _group_must_be_ignored(
            transport,
            label=label,
            allowed=result.allowed,
            reason=result.reason,
            baseline_tools=before_tools,
            baseline_outbound=before_out,
        )
        if err:
            failures.append(err)
        elif result.reason != "groups_disabled":
            # group JID / broadcast should still classify as groups_disabled
            failures.append(f"{label}: expected groups_disabled got {result.reason}")

    if broken:
        # If we didn't already fail above, force the classic assertion path.
        sim = IngressSimulator(
            allowlist=allowlist,
            catcher=OutboundMessageCatcher(),
            groups_enabled=False,
            broken_allow_all=True,
        )
        result = sim.handle(allowlist[0], "group noise", is_group=True)
        if result.allowed or result.tool_calls or sim.catcher.count():
            return _fail(
                f"group message produced effects while groups disabled "
                f"(allowed={result.allowed}, tools={result.tool_calls!r}, "
                f"outbound={sim.catcher.count()}, reason={result.reason})"
            )
        return _fail(
            "broken_allow_all did not surface group side effects — fail-closed proof weak"
        )

    # Mixed: allowlisted DM then group — DM may increment; group must not.
    mixed = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        groups_enabled=False,
    )
    dm = mixed.inject_text(OWNER, "real dm")
    if not dm.allowed or mixed.counters.tool_calls < 1:
        failures.append("mixed: allowlisted DM should run before group probe")
    tools_after_dm = mixed.counters.tool_calls
    out_after_dm = mixed.counters.outbound_sends
    grp = mixed.inject(
        InboundWhatsAppMessage(
            sender=OWNER,
            body="now in group",
            is_group=True,
            group_id="g-mixed",
        )
    )
    if grp.allowed or mixed.counters.tool_calls != tools_after_dm:
        failures.append(
            f"mixed: group changed tools {tools_after_dm}→{mixed.counters.tool_calls}"
        )
    if mixed.counters.outbound_sends != out_after_dm:
        failures.append(
            f"mixed: group changed outbound {out_after_dm}→{mixed.counters.outbound_sends}"
        )

    # Default groups_enabled must be False
    default_sim = IngressSimulator(allowlist=allowlist, catcher=OutboundMessageCatcher())
    if default_sim.groups_enabled:
        failures.append("default groups_enabled must be False")

    if failures:
        return _fail("; ".join(failures))

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "groups ignored (is_group, group_id, @g.us, broadcast); "
            "DM positive path unaffected; counters stable on group"
        ),
    }
