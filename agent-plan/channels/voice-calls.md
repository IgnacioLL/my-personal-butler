# Voice calls

## Purpose

Let the agent **call you** for high-importance reminders or short conversations when WhatsApp pings are not enough.

## Why calls exist

WhatsApp is great for async. Calls are for:

- “Call grandma in 10 minutes” escalations
- morning accountability when you ignore chats
- quick verbal clarification while driving / busy
- rare urgent confirmations

## Scope (v1)

- Outbound calls initiated by cron/reminder or explicit “call me”
- Short scripted or semi-live conversation
- Mostly **read-only tools** during the call (calendar lookup, read todos)
- After-call writebacks: create tasks, send WhatsApp summary

## Out of scope (v1)

- Buying, booking, or applying self-mod patches during a live call
- Open inbound from anyone
- Long therapy-style calls as the default interface

## Provider direction

Use OpenClaw `@openclaw/voice-call` with **Twilio** (or **Telnyx**):

- dedicated number (`fromNumber`)
- public HTTPS webhook to Gateway (`publicUrl` → `/voice/webhook`)
- outbound allowlist locked to the operator handset (`toNumber`)
- inbound disabled in v1 (`inboundPolicy: disabled`); caller-ID allowlist only if inbound is enabled later

Production templates + runbook:

- [`config/production/openclaw.voice-call.json`](../../config/production/openclaw.voice-call.json)
- [`config/production/voice-call.env.example`](../../config/production/voice-call.env.example)
- [`config/production/call-mode.policy.json`](../../config/production/call-mode.policy.json)
- [`src/skills/voice-calls/`](../../src/skills/voice-calls/)
- [`docs/voice-calls.md`](../../docs/voice-calls.md)

CI / harness keeps `MockVoiceProvider` (`provider: mock`) — no live carriers in `test:ci`.

## Safety rules

1. Call mode tool allowlist is narrow (`INV-APPR-005`)
2. Any mutating action becomes a post-call approval/task (including code-change proposals)
3. Quiet hours respected unless marked emergency
4. Cap call frequency (avoid spam loops)
5. Outbound dial only numbers on the operator allowlist

### Call-mode tool allowlist (`INV-APPR-005`)

| Allowed mid-call | Forbidden mid-call |
| --- | --- |
| `calendar_read`, `memory_read`, `todo_read`, `source_read` | `buy`, `book`, `self_mod_apply` (and any non-allowlisted mutator) |

Forbidden hard actions return `call_mode_forbidden_hard_action`. Policy files:
`src/skills/voice-calls/policy.json`, `config/production/call-mode.policy.json`,
`src/channels/voice/allowlist.py`.

## Flow

```text
Reminder fires → policy says "call"
  → place outbound call (allowlisted operator number)
  → speak reminder / ask yes-no (read-only tools only)
  → write outcome to todos/memory
  → send WhatsApp summary (kind=after_call_summary)
```

## Acceptance criteria

- [x] Agent can place an outbound call to your number (production: OpenClaw plugin + allowlist; CI: mock provider)
- [x] Call content is grounded in the triggering reminder
- [x] No purchase/booking/self-mod-apply tools available mid-call (`INV-APPR-005`)
- [x] Call creates an auditable after-call WhatsApp note
