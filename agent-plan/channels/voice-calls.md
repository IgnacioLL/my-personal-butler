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

Use OpenClaw voice-call plugin with Twilio (or Telnyx/Plivo):

- dedicated number
- public webhook to Gateway
- caller-ID allowlist if inbound is enabled later

## Safety rules

1. Call mode tool allowlist is narrow
2. Any mutating action becomes a post-call approval/task (including code-change proposals)
3. Quiet hours respected unless marked emergency
4. Cap call frequency (avoid spam loops)

## Flow

```text
Reminder fires → policy says "call"
  → place outbound call
  → speak reminder / ask yes-no
  → write outcome to todos/memory
  → send WhatsApp summary
```

## Acceptance criteria

- [ ] Agent can place an outbound call to your number
- [ ] Call content is grounded in the triggering reminder
- [ ] No purchase/booking/self-mod-apply tools available mid-call
- [ ] Call creates an auditable after-call note
