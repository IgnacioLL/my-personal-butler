# Personal memory

## Purpose

Make the agent know you well enough to plan without re-asking basics: likes, diet constraints, family rituals, travel wishes, budget vibes, preferred booking times, etc.

## Memory buckets

| Bucket | Examples | Hot in prompt? |
| --- | --- | --- |
| Identity | name, language, household, grandmother relationship | Yes |
| Preferences | food likes, brands, haircut style, quiet hours | Yes (compact) |
| Goals | diet phase, trip ideas, habit targets | Yes |
| Procedures | how you approve spends, how to book Booksy | As skills |
| Episodic | past chats, what happened last Tuesday | Search on demand |
| Secrets | credentials | Never in casual memory; use secret store |

## Write policy

The agent should persist a fact when:

- you explicitly say “remember…”
- a preference repeats twice
- a constraint affects safety/health (allergies, hard budget)
- a completed booking reveals a stable preference (“always Saturdays”)

Ask before storing sensitive personal data that isn’t clearly meant to be kept.

## Read policy

- Always load compact identity + active goals
- Retrieve episodic/procedural memory when relevant to the task
- Don’t dump entire history into every Luna turn

## Hermes-inspired practices (on OpenClaw)

Even though runtime is OpenClaw, copy these habits:

1. Curated `USER` / profile file for durable facts
2. Session search / recall for older context
3. Skills as procedural memory (“Booksy haircut flow”)
4. Periodic “what should we remember from this week?” review

## Seed profile (to fill later)

- People that matter + how to contact rituals (e.g. call grandma Sundays)
- Diet rules / dislikes / allergies
- Typical week shape and quiet hours
- Cities / travel wishlist
- Grooming / health providers (Booksy shops)
- Spend comfort (caps, merchants)

## Acceptance criteria

- [ ] Agent can answer “what do you know about my diet?” from memory
- [ ] Reminder language can use personal context (“grandma”, not only raw phone tasks)
- [ ] New stable prefs survive restart
- [ ] Secrets are not mixed into chat memory files
