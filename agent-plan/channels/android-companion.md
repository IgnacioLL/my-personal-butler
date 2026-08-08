# Android companion

## Purpose

A lightweight control surface paired to the OpenClaw Gateway:

- to-do / habit list you can tap
- push notifications
- Accept / Deny / Edit for risky agent actions
- optional quick actions (“snooze”, “mark done”, “pause agent”)

## Design stance

The Android app is **not** a second chatbot brain.

- WhatsApp = conversation
- Android = lists + approvals + status

Prefer OpenClaw’s Android node / companion patterns before building a fully custom app. Custom UI only if stock companion cannot cover todos + approvals well enough.

## Core screens (v1)

1. **Inbox / Approvals** — pending actions with Accept, Deny, Edit
2. **Todos** — open tasks, due dates, completion
3. **Habits** — recurring personal commitments
4. **Status** — gateway online, agent paused?, spend freeze?

## Approval UX

Each pending item should show:

- what the agent wants to do (plain language)
- why (your request / reminder context)
- cost / time / merchant if relevant
- expiry (“auto-cancels in 2h”)
- actions: Accept once / Deny / Edit details

See [../trust-and-safety/approval-matrix.md](../trust-and-safety/approval-matrix.md).

## Sync model

- Gateway owns canonical task + approval state
- Android is a paired node that renders and acknowledges
- WhatsApp can create todos; Android completes them
- Completing a todo notifies the agent session if useful

## Notifications

| Event | Notification |
| --- | --- |
| Hard approval needed | High priority push |
| Reminder due | Normal |
| Booking confirmed | Normal |
| Agent paused / error | High |

## Acceptance criteria

- [ ] Device paired securely to your Gateway
- [ ] Pending purchase/booking appears with Accept/Deny
- [ ] Denied actions never execute
- [ ] Todo created via WhatsApp appears on Android
- [ ] Todo completed on Android is reflected in agent state
