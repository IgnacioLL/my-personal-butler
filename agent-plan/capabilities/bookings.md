# Bookings (Booksy and similar)

## Purpose

Have the agent find and reserve real-world appointments (haircut, barber, spa, etc.), especially via sites like Booksy.

## Scope

### v1.5
- Browse availability for a known provider/shop from memory
- Propose 2–3 slots that fit calendar + prefs
- Hard approve → complete booking
- Write calendar event + confirmation message

### Later
- Discover new providers
- Reschedule/cancel flows
- Multi-person bookings

## Flow

```text
User ask (WhatsApp)
  → read prefs (shop, stylist, duration, time windows)
  → read calendar free slots
  → browser skill checks Booksy availability
  → propose options
  → Android/WhatsApp hard approve
  → execute reservation
  → confirm + calendar write
```

## Approval

Always **hard approve** before submitting a reservation.

Approval card must show:

- shop / service
- date-time
- estimated price if known
- cancellation policy snippet if available

## Failure handling

- Site changed / captcha / login required → stop and ask you to take over, keep proposed times
- Slot disappears → offer next best alternatives
- Never retry-book aggressively (double booking risk)

## Skill contents

- provider URL(s)
- login strategy (manual session / saved profile — decide carefully)
- preferred services list
- backup shops

## Acceptance criteria

- [ ] Agent proposes valid slots that don’t conflict with calendar
- [ ] No booking without Accept
- [ ] Successful booking produces WhatsApp confirmation + calendar event
- [ ] Failed booking never leaves a false “done” state
