# WhatsApp channel

## Purpose

Primary way to talk to the agent: text, voice notes, and later interactive approval buttons / quick replies.

## Scope (v1)

- Personal DM only (your number allowlisted)
- Inbound text
- Inbound voice notes → mandatory transcription
- Outbound text replies
- Outbound voice replies when inbound was audio (inbound TTS mode)
- Images/docs later if useful (receipts, screenshots of Booksy)

## Out of scope (v1)

- Group chats
- Acting as you in other people’s threads
- Unrestricted contact with third parties via WhatsApp

## UX principles

- Voice-first frictionless: speak → get action/plan
- Echo a short transcript when confidence is uncertain or stakes are high
- Keep replies scannable; long plans as bullet lists
- For approvals, prefer buttons over “reply YES”

## Technical notes (OpenClaw)

- Configure WhatsApp channel on the Gateway
- `allowFrom` locked to your number
- Media pipeline: audio always transcribed before agent turn
- Prefer TTS reply mode `inbound` (speak back only if you spoke)

Details for STT: [../intelligence/transcription.md](../intelligence/transcription.md)

## Example flows

### Reminder

> You (audio): “Remind me Sunday to call grandma.”  
> Agent: creates reminder + confirms time/timezone.

### Booking proposal

> You: “Book a haircut next week afternoon.”  
> Agent: checks calendar → finds Booksy slots → sends proposal + Android approval.

### Correction

> Agent echoed wrong transcript → you reply “No — I said low carb, not no carb” → agent updates memory and plan.

## Acceptance criteria

- [ ] Only your number can talk to the agent
- [ ] Voice notes reliably become text turns
- [ ] Agent can create reminders from a single audio
- [ ] Risky actions never execute from WhatsApp alone without approval
