# Channels

Surfaces where you interact with the agent. All channels talk to the **same** OpenClaw Gateway and share memory + approval policy.

## Channel roles

| Channel | Role | Priority |
| --- | --- | --- |
| WhatsApp | Primary conversation (text + audio) | P0 |
| Android companion | Todos, habit list, Accept/Deny | P0 |
| Phone calls | High-salience talk / reminders | P1 |
| Web Control UI | Admin / debugging only | P2 |

## Rules shared by all channels

1. Allowlist your identity (phone number / paired device)
2. Same approval matrix ([../trust-and-safety/approval-matrix.md](../trust-and-safety/approval-matrix.md))
3. Same memory store
4. Prefer short confirmations over essays
5. Never treat a channel as a separate agent personality

## Documents

- [WhatsApp](./whatsapp.md) — main conversational interface
- [Voice calls](./voice-calls.md) — agent calls you / limited inbound
- [Android companion](./android-companion.md) — todos + approvals UI

## Build order

1. WhatsApp DM + transcription
2. Android pairing for approvals/todos
3. Outbound calls for important reminders
4. Optional inbound call allowlist later
