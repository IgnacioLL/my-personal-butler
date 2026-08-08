# Platform choice: OpenClaw vs Hermes

## Recommendation

**Use OpenClaw as the primary runtime.**

Hermes remains a useful reference for memory design (multi-tier personal modeling, skill self-improvement), but it is not the best shell for this product.

## Comparison against our requirements

| Requirement | OpenClaw | Hermes | Winner |
| --- | --- | --- | --- |
| WhatsApp as main channel | Mature first-class channel | Supported, less life-agent focused | OpenClaw |
| Voice notes STT/TTS | Built-in media/voice path | Possible, more assembly | OpenClaw |
| Agent calls you | Voice-call plugin (Twilio/Telnyx/Plivo) | Not a core surface | OpenClaw |
| Android companion + approvals | Native Android node + remote approvals | Weak / DIY | OpenClaw |
| Codex subscription + Luna | Native OpenAI/Codex provider path | Generic endpoint wiring | OpenClaw |
| Cron / proactive nudges | Cron + Heartbeat | Cron | Tie / slight OpenClaw |
| Browser bookings | Browser tools + skills | Tools / MCP | Tie |
| Deep personal memory | Good, needs discipline | Stronger built-in learning loop | Hermes |
| Long-running remote compute | Gateway on VPS/home | Excellent (Docker/SSH/Modal) | Hermes |

## Why OpenClaw wins for us

Our product is defined by **interfaces and trust**:

1. WhatsApp audio in
2. phone call out
3. Android Accept/Deny
4. Codex/Luna credits

OpenClaw already productizes that shape as a personal Gateway.

Hermes optimizes for an agent that improves itself over long autonomous runs. Valuable later; not the blocker for v1.

## What we borrow from Hermes

Even while running on OpenClaw, adopt Hermes-style memory hygiene:

- hot profile always in context (`USER` / identity facts)
- searchable episodic history
- procedural skills (“how I book a haircut”)
- periodic nudge to persist useful facts

See [intelligence/memory.md](./intelligence/memory.md).

## Revisit criteria

Reconsider Hermes (or a hybrid) if:

- memory quality becomes the main failure mode after v1
- we need heavy long-running research jobs more than mobile UX
- OpenClaw’s approval/call/WhatsApp path proves insufficient

Until then: **one runtime = OpenClaw**.
