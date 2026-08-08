# Approval matrix

## Tiers

| Tier | Meaning | UX |
| --- | --- | --- |
| **Auto** | safe / reversible / cheap | just do it; optional short confirm |
| **Soft confirm** | mutates your schedule/data | WhatsApp quick confirm or Android |
| **Hard approve** | money or external commitment | Android push + Accept/Deny/Edit; WhatsApp backup |
| **Forbidden** | never without redesign | refuse + explain |

## Matrix

| Action | Tier |
| --- | --- |
| Read calendar / memory / todos | Auto |
| Create reminder / habit | Auto |
| Draft diet plan | Auto |
| Add todo | Auto |
| Send WhatsApp reply to you | Auto |
| Create calendar event | Soft |
| Modify/cancel your event | Soft |
| Update personal memory prefs | Soft (or Auto for explicit “remember…”) |
| Book Booksy / external appointment | Hard |
| Buy anything | Hard |
| Message third parties as you | Hard / Forbidden in v1 |
| Transfer money / subscriptions | Forbidden until explicit design |
| Disable spend freeze / raise caps | Hard (and intentional UI) |

## Approval item schema

- id
- created_at / expires_at
- action_type
- summary (human)
- payload (machine)
- estimated_cost?
- source_channel / source_utterance
- status: pending | accepted | denied | expired | executed | failed

## Expiry policy

- Default hard approvals expire in a few hours (configurable)
- On expiry: notify once, mark expired, do not execute
- Re-propose only on user request or new explicit intent

## Channel rules

- WhatsApp can create soft confirms
- Hard approvals should preferentially land on Android
- Voice calls never hard-execute; they create post-call approvals/tasks

## Kill switches

- `pause agent` — no proactive work, replies “paused”
- `freeze spending` — shopping skill cannot execute
- `cancel pending` — all pending approvals → cancelled
