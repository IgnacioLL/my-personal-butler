"""INV-INGRESS-001 — non-allowlisted WhatsApp sender: no tools, no outbound.

Adversarial contract coverage (TASK-03): spoofed sender forms, empty allowlist,
empty/blank sender, substring/prefix spoofs, multi-message floods — all must
leave tool-call and outbound side-effect counters at zero.
"""

from __future__ import annotations

from typing import Any

from harness.ingress_sim import IngressSimulator
from harness.outbound import OutboundMessageCatcher
from harness.whatsapp_transport import InboundWhatsAppMessage, MockWhatsAppTransport

INV_ID = "INV-INGRESS-001"
DESCRIPTION = (
    "Non-allowlisted WhatsApp sender produces no agent tools and no outbound side effects"
)

OWNER = "+15550001111"


def _fail(detail: str) -> dict[str, Any]:
    return {"id": INV_ID, "result": "FAIL", "detail": detail}


def _assert_no_effects(
    transport: MockWhatsAppTransport,
    *,
    label: str,
    result_allowed: bool,
    reason: str,
) -> str | None:
    snap = transport.counters.snapshot()
    if result_allowed:
        return f"{label}: incorrectly allowed (reason={reason})"
    if snap["tool_calls"] or snap["outbound_sends"] or snap["hard_action_attempts"]:
        return (
            f"{label}: side effects after reject "
            f"(counters={snap}, reason={reason}, tools={transport.tool_call_log!r})"
        )
    if transport.catcher.count():
        return f"{label}: outbound catcher non-empty ({transport.catcher.count()})"
    return None


def check(ctx: dict[str, Any]) -> dict[str, Any]:
    allowlist = list(ctx.get("allowlist") or [OWNER])
    broken = bool(ctx.get("broken_allow_all", False))
    failures: list[str] = []

    # --- Case A: basic non-allowlisted DM ---
    catcher = OutboundMessageCatcher()
    transport = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=catcher,
        groups_enabled=False,
        broken_allow_all=broken,
    )
    r = transport.inject_text("+19999999999", "please buy groceries")
    err = _assert_no_effects(
        transport, label="stranger", result_allowed=r.allowed, reason=r.reason
    )
    if err:
        failures.append(err)
    elif r.reason not in {"sender_not_allowlisted", "broken_allow_all"} and not broken:
        # broken mode may allow; non-broken must name the reject reason
        if not r.allowed and r.reason != "sender_not_allowlisted":
            failures.append(f"stranger: unexpected reason={r.reason}")

    # --- Case B: adversarial spoof / format variants ---
    transport.reset_effects()
    spoofs = [
        ("", "empty_sender"),
        ("   ", "blank_sender"),
        ("\u200b+15550001111", "zwsp_owner_lookalike"),  # invisible then owner digits without exact match after strip... wait, after strip of zwsp this BECOMES owner
        ("+15550001111\u200b", "zwsp_suffix"),
        ("+15550001112", "off_by_one"),
        ("15550001111", "missing_plus"),
        ("whatsapp:+15550001111", "jid_prefix"),
        ("+15550001111 ", "trailing_space_ok_or_spoof"),  # normalize should allow if owner
        ("++15550001111", "double_plus"),
        ("+1 555 000 1111", "spaced_digits"),
        ("+15550001111@c.us", "device_jid"),
        (OWNER + "x", "suffix_char"),
        ("x" + OWNER, "prefix_char"),
        ("+19999999999", "explicit_stranger"),
    ]

    # After normalize, pure whitespace/zwsp around exact OWNER digits should match allowlist.
    # Those are NOT spoofs — they are canonicalization. Track expected allow vs deny.
    expect_allow_after_normalize = {
        "zwsp_owner_lookalike",  # \u200b stripped → OWNER
        "zwsp_suffix",
        "trailing_space_ok_or_spoof",
    }

    for sender, label in spoofs:
        transport.reset_effects()
        result = transport.inject_text(sender, f"spoof:{label}")
        if label in expect_allow_after_normalize:
            # Positive control: invisible/space padding around real owner is allowlisted DM.
            if broken:
                continue
            if not result.allowed:
                failures.append(
                    f"{label}: owner with padding should allow after normalize "
                    f"(reason={result.reason})"
                )
            elif transport.counters.tool_calls < 1 or transport.catcher.count() < 1:
                failures.append(f"{label}: allowlisted path produced no effects")
            continue

        err = _assert_no_effects(
            transport, label=label, result_allowed=result.allowed, reason=result.reason
        )
        if err:
            failures.append(err)

    # --- Case C: empty allowlist rejects everyone (including former owner) ---
    empty = MockWhatsAppTransport(
        allowlist=[],
        catcher=OutboundMessageCatcher(),
        groups_enabled=False,
        broken_allow_all=broken,
    )
    er = empty.inject_text(OWNER, "should not run")
    if broken:
        pass  # fail-closed proof forces allow
    else:
        err = _assert_no_effects(
            empty, label="empty_allowlist", result_allowed=er.allowed, reason=er.reason
        )
        if err:
            failures.append(err)
        elif er.reason != "empty_allowlist":
            failures.append(f"empty_allowlist: expected reason empty_allowlist got {er.reason}")

    # --- Case D: flood of non-allowlisted messages — counters stay zero ---
    flood = MockWhatsAppTransport(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        groups_enabled=False,
        broken_allow_all=broken,
    )
    for i in range(5):
        flood.inject(
            InboundWhatsAppMessage(
                sender=f"+1999000{i:04d}",
                body=f"flood {i}: buy now",
                media_type="text",
            )
        )
    if not broken:
        err = _assert_no_effects(
            flood,
            label="flood",
            result_allowed=False if flood.counters.total == 0 else True,
            reason="flood",
        )
        # _assert_no_effects checks allowed flag; force via counters only:
        snap = flood.counters.snapshot()
        if snap["tool_calls"] or snap["outbound_sends"] or flood.catcher.count():
            failures.append(f"flood: side effects counters={snap}")

    # --- Case E: IngressSimulator wrapper still isolates ---
    sim = IngressSimulator(
        allowlist=allowlist,
        catcher=OutboundMessageCatcher(),
        groups_enabled=False,
        broken_allow_all=broken,
    )
    sim_result = sim.handle("+18887776666", "invoke tools please")
    if not broken and (
        sim_result.allowed or sim_result.tool_calls or sim.catcher.count() or sim.counters.total
    ):
        failures.append(
            f"sim_wrapper: effects on reject "
            f"(allowed={sim_result.allowed}, tools={sim_result.tool_calls!r}, "
            f"outbound={sim.catcher.count()}, counters={sim.counters.snapshot()})"
        )

    # --- Positive control: allowlisted DM does produce tools+outbound (proves not total lockout)
    if not broken:
        pos = MockWhatsAppTransport(allowlist=allowlist, catcher=OutboundMessageCatcher())
        ok = pos.inject_text(OWNER, "ping")
        if not ok.allowed or pos.counters.tool_calls < 1 or pos.catcher.count() < 1:
            failures.append(
                f"positive_control: allowlisted DM should run "
                f"(allowed={ok.allowed}, counters={pos.counters.snapshot()})"
            )

    if failures:
        return _fail("; ".join(failures))

    # broken_allow_all: stranger must be allowed → this INV must FAIL (fail-closed proof)
    if broken:
        broken_catcher = OutboundMessageCatcher()
        broken_t = MockWhatsAppTransport(
            allowlist=allowlist,
            catcher=broken_catcher,
            broken_allow_all=True,
        )
        br = broken_t.inject_text("+19999999999", "broken path")
        if br.allowed and (broken_t.counters.tool_calls or broken_catcher.count()):
            return _fail(
                f"non-allowlisted sender caused side effects "
                f"(tools={broken_t.tool_call_log!r}, outbound={broken_catcher.count()}, "
                f"reason={br.reason})"
            )
        if br.allowed:
            return _fail(
                f"non-allowlisted sender incorrectly allowed (reason={br.reason})"
            )

    return {
        "id": INV_ID,
        "result": "PASS",
        "detail": (
            "rejected non-allowlisted/spoof/empty-allowlist/flood; "
            "tool_calls=0 outbound=0; allowlisted positive control ok"
        ),
    }
