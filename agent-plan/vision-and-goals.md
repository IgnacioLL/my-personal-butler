# Vision and goals

## What we are building

A personal life agent that lives where you already talk — mainly WhatsApp — and can:

- remember personal context (preferences, family, travel wants, diet rules)
- remind and follow up (call grandmother, stick to diet)
- plan (meals, weeks, trips)
- look at the calendar and schedule
- do things for you (Booksy haircut, purchases) only after you accept
- call you when a nudge needs a real conversation
- show a simple Android surface for todos and approvals

## Product north star

It should feel like a competent personal agent, not a chatbot with plugins.

Success means:

- you can send a WhatsApp voice note and get a useful reply without typing
- recurring life tasks happen without you re-explaining context
- the agent proposes actions; you stay in control of money and bookings
- the Android app is the checklist/control panel, not a second personality

## Non-goals (for v1)

- multi-user / family shared agent
- fully autonomous spending
- replacing every app UI with chat
- building a custom agent runtime from scratch

## Personas of the agent

| Mode | Behavior |
| --- | --- |
| Companion | chat, remember, advise |
| Secretary | calendar, reminders, todos |
| Operator | book, buy, browse — gated |
| Coach | diet / habit accountability |

## Perfect-agent checklist

Include these to feel complete:

1. WhatsApp text + audio as the default interface
2. Reliable transcription pipeline
3. Outbound phone calls for high-priority reminders
4. Android todos + Accept/Deny notifications
5. Calendar read/write with conflict awareness
6. Structured personal memory (identity, prefs, goals, procedures)
7. Booking skill (Booksy-class sites) behind hard approve
8. Shopping skill behind hard approve + spend caps
9. Diet/planning skill tied to calendar and grocery reality
10. Proactive heartbeat (morning brief, habit nudges, weekly review)
11. Kill switches: pause agent, cancel pending approvals, freeze spending

## Constraints

- Prefer OpenClaw Gateway over custom orchestration
- Use Codex subscription credits; default to Luna
- Always keep a transcription model in the path for WhatsApp audio
- Safety > cleverness for any action that spends money or books externally
