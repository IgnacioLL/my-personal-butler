# Roadmap

Phased plan. No calendar-day estimates — phases are capability unlocks.

## Phase 0 — Foundations

- Decide OpenClaw + Luna + STT (done in plan)
- Host Gateway ([hosting.md](./hosting.md))
- Seed personal memory profile template
- Kill switches designed

**Exit:** Gateway up; you can DM it from WhatsApp text.

## Phase 1 — Voice + memory + reminders

- WhatsApp audio transcription path
- Basic personal memory read/write
- One-shot + recurring reminders
- Optional TTS replies for inbound audio

**Exit:** “Remind me Sunday to call grandma” works from a voice note.

## Phase 2 — Android control plane

- Pair Android companion/node
- Todos sync
- Approval inbox UI wired (even if few hard actions yet)
- Soft confirm for calendar writes

**Exit:** WhatsApp-created todo appears on Android; calendar event needs confirm.

## Phase 3 — Calendar-aware planning

- Reliable calendar read
- Conflict-aware scheduling suggestions
- Diet plan v1 using memory + schedule
- Habit check-ins

**Exit:** Agent can plan a day that respects calendar + diet prefs.

## Phase 4 — Calls

- Outbound Twilio (or equiv) calls for high-priority reminders
- After-call WhatsApp summary
- Call tool allowlist (no buy/book)

**Exit:** Ignored grandma reminder can escalate to a call per policy.

## Phase 5 — Bookings

- Booksy (or chosen provider) browser skill
- Hard approve cards
- Calendar writeback on success

**Exit:** Haircut proposal → Accept → booked + on calendar.

## Phase 6 — Shopping

- Propose-only shopping skill
- Spend caps + freeze
- Hard approve execute path
- Receipt logging

**Exit:** Rebuy a known item end-to-end under caps.

## Phase 7 — Self-modification

- Read-only exploration of allowlisted repo paths
- Diff proposal skill (docs/skills first)
- Hard-approve apply path with rollback refs
- `freeze self-mod` kill switch
- Policy-change subtype for approval-matrix / safety code
- Optional Gateway reload as a separate Approve

**Exit:** You can ask the agent to patch a skill; it shows a diff; Accept applies on a branch; Deny does nothing.

## Phase 8 — Polish / “perfect”

- Weekly review ritual (memory hygiene)
- Morning brief heartbeat
- Better proactive quiet policies
- Evaluate Hermes-like memory upgrades if gaps remain
- Harden backups, audits, injection defenses
- Tighten self-mod checks (tests before apply, auto-revert option)

## Tracking

Update this file when a phase exits. Keep decisions in the relevant leaf docs rather than inventing parallel trackers.

Phase exits also require the matching unlock in [testing/roadmap.md](../testing/roadmap.md) (harness CI green — not “worked once on my phone”).
