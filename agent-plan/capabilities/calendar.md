# Calendar

## Purpose

Let the agent see your availability and schedule things without colliding with real life.

## Scope (v1)

- Read primary calendar
- Propose events
- Create/update/cancel with **soft confirmation**
- Respect quiet hours / buffers when planning

## Intents

- “What’s on my calendar tomorrow?”
- “Schedule deep work Friday morning”
- “Find an afternoon next week for a haircut”
- “Move my dentist appointment” (later if provider allows)

## Write policy

| Action | Tier |
| --- | --- |
| Read | Auto |
| Create event | Soft confirm |
| Modify/cancel | Soft confirm |
| Invite other people | Hard approve (later) |

## Planning heuristics

- Prefer your historically liked time windows (from memory)
- Leave travel buffers for physical appointments
- When booking external services, hold a tentative local event only after approval strategy is clear

## Integrations

Start with Google Calendar (or whatever you already use). Keep provider-specific details in implementation notes later.

## Acceptance criteria

- [ ] Agent can summarize upcoming events accurately
- [ ] Agent refuses to double-book without calling it out
- [ ] Event creation requires confirmation
- [ ] Timezone handling is correct
