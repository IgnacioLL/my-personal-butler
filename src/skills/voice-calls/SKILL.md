# Voice calls — production skill

## Purpose

Place short outbound calls to the **operator number** for high-importance
reminders / escalations when WhatsApp pings are not enough. Aligns with
[`agent-plan/channels/voice-calls.md`](../../../agent-plan/channels/voice-calls.md).

## Production path

- OpenClaw plugin: `@openclaw/voice-call` (Twilio or Telnyx)
- Config fragment: [`config/production/openclaw.voice-call.json`](../../../config/production/openclaw.voice-call.json)
- Secrets template: [`config/production/voice-call.env.example`](../../../config/production/voice-call.env.example)
- Call-mode policy: [`policy.json`](./policy.json) (`INV-APPR-005`)
- Runbook: [`docs/voice-calls.md`](../../../docs/voice-calls.md)

CI keeps [`MockVoiceProvider`](../../channels/voice/provider.py) — never live carriers in `test:ci`.

## Tools (call mode)

| Tool | Mid-call |
| --- | --- |
| `calendar_read` / `memory_read` / `todo_read` / `source_read` | allow |
| `buy` / `book` / `self_mod_apply` | **forbid** (`call_mode_forbidden_hard_action`) |
| Other mutators | forbid (`call_mode_tool_not_allowlisted`) → post-call task/approval |

## After call

1. Write outcome to todos/memory as needed (post-call).
2. Queue a WhatsApp summary (`kind=after_call_summary`) to the operator DM.
3. Any purchase / booking / self-mod intent becomes a hard-approval item — never executed mid-call.

## Outbound allowlist

Only dial numbers listed in `VOICE_CALL_OUTBOUND_ALLOWLIST` / `personalButler.voiceCalls.outboundAllowlist` (operator handset).
