# Diet and planning

## Purpose

Help create realistic diets/meal plans and follow through — not just dump a generic macro sheet.

## Scope (v1 basic)

- Capture diet goals + constraints into memory
- Generate a short meal plan (day/week)
- Align meals with calendar reality (late nights, travel days)
- Create grocery todo list
- Habit check-ins (“did you follow today’s plan?”)

## Out of scope (v1)

- Medical nutrition therapy claims
- Automatic grocery checkout (that’s shopping capability later)
- Perfect macro tracking app replacement

## Inputs the agent should use

- preferences / dislikes / allergies (memory)
- current goal (cut / maintain / whatever you state)
- schedule constraints
- cooking time budget
- leftover / repeat-meal tolerance

## Outputs

- plan summary on WhatsApp
- meals as structured notes
- grocery todos on Android
- reminders for prep / check-in

## Accountability loop

1. Plan created
2. Reminder at agreed time
3. You reply done / skipped / swapped
4. Agent adapts next day without shame-spam

## Acceptance criteria

- [ ] Agent can generate a plan that respects stored dislikes
- [ ] Plan creates actionable grocery todos
- [ ] Check-in reminder fires
- [ ] Preference updates persist for the next plan
