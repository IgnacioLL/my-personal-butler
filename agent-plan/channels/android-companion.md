# Android companion

## Purpose

A lightweight control surface paired to the OpenClaw Gateway:

- to-do / habit list you can tap
- push notifications
- Accept / Deny / Edit for risky agent actions (purchases, bookings, **source diffs**)
- optional quick actions (“snooze”, “mark done”, “pause agent”, “freeze self-mod”)

## Design stance

The Android app is **not** a second chatbot brain.

- WhatsApp = conversation
- Android = lists + approvals + status

Prefer OpenClaw’s Android node / companion patterns before building a fully custom app. Custom UI only if stock companion cannot cover todos + approvals well enough.

## Production wiring (PROD-05)

| Artifact | Role |
| --- | --- |
| [`docs/android-pairing.md`](../../docs/android-pairing.md) | Pair phone → Gateway; operator smoke checklist |
| [`config/android.example.yaml`](../../config/android.example.yaml) | Production control plane: todos, inbox, Status/kill switches, self-mod cards |
| [`config/android.harness.json`](../../config/android.harness.json) | CI doubles map (`src/channels/android/*`) — keep `make test-ci` green |

Live path: official OpenClaw Android app (`role: node`) → device approve (`openclaw devices approve`) → node connected (`openclaw nodes status`) over LAN `ws://` or Tailscale/`wss://`. Gateway owns canonical todos + approvals; Android renders and acknowledges.

## Core screens (v1)

1. **Inbox / Approvals** — pending actions with Accept, Deny, Edit
2. **Todos** — open tasks, due dates, completion
3. **Habits** — recurring personal commitments
4. **Status** — gateway online, agent paused?, spend freeze?, self-mod freeze?, cancel pending

## Approval UX

Each pending item should show:

- what the agent wants to do (plain language)
- why (your request / reminder context)
- cost / time / merchant if relevant
- for self-mod: files touched + diff preview + rollback ref
- badge: **Code change** (self-mod) or **policy-change** (louder)
- expiry (“auto-cancels in 2h”)
- actions: Accept once / Deny / Edit details

Self-mod approvals should be visually distinct from shopping/booking (e.g. “Code change” badge / policy-change warning).

See [../trust-and-safety/approval-matrix.md](../trust-and-safety/approval-matrix.md) and [../capabilities/self-modification.md](../capabilities/self-modification.md).

## Sync model

- Gateway owns canonical task + approval state
- Android is a paired node that renders and acknowledges
- WhatsApp can create todos; Android completes them
- Completing a todo notifies the agent session if useful

## Kill switches (Status screen)

| Control | Effect |
| --- | --- |
| Pause agent | No proactive work |
| Freeze spending | Shopping execute blocked |
| Freeze self-mod | Source write/apply tools disabled |
| Cancel pending | All pending approvals → cancelled |

## Notifications

| Event | Notification |
| --- | --- |
| Hard approval needed | High priority push |
| Self-mod / policy-change approval | High priority push |
| Reminder due | Normal |
| Booking confirmed | Normal |
| Agent paused / error | High |

## Operator checklist (summary)

Full steps: [`docs/android-pairing.md`](../../docs/android-pairing.md).

1. Pair phone to Gateway (device + node approve).
2. WhatsApp “add todo…” → appears on Android Todos.
3. Hard action → Inbox card → **Deny** never executes; **Accept** executes once.

## Acceptance criteria

- [ ] Device paired securely to your Gateway
- [ ] Pending purchase/booking/self-mod appears with Accept/Deny
- [ ] Self-mod card can show a diff summary (+ badge)
- [ ] Denied actions never execute
- [ ] Todo created via WhatsApp appears on Android
- [ ] Todo completed on Android is reflected in agent state
- [ ] Status exposes pause / freeze spending / freeze self-mod / cancel pending
- [ ] Production config + pairing runbook exist; CI still uses API doubles
