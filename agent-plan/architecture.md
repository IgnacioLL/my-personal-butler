# Architecture

## One-sentence architecture

An always-on **OpenClaw Gateway** is the control plane; WhatsApp / calls / Android are surfaces; Luna is the default brain; tools and skills do work; an approval layer gates money and external side effects.

## Context diagram

```text
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  WhatsApp    │  │ Phone calls  │  │ Android app  │
│ text + audio │  │ Twilio/etc.  │  │ todos+OK/NO  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └────────────┬────┴─────────────────┘
                    ▼
         ┌─────────────────────┐
         │  OpenClaw Gateway   │
         │  sessions/routing   │
         │  STT / TTS / media  │
         │  approval queue     │
         │  cron / heartbeat   │
         └──────────┬──────────┘
                    ▼
         ┌─────────────────────┐
         │  Agent (Luna+)      │
         │  tools + skills     │
         └──────────┬──────────┘
                    ▼
    ┌──────────┬──────────┬──────────┬──────────┐
    ▼          ▼          ▼          ▼          ▼
 Calendar   Browser    Memory     Todos     Commerce
 (Google)   (Booksy)   (you)    (Android)  (approve)
```

## Layers

| Layer | Responsibility | Docs |
| --- | --- | --- |
| Surfaces | how you talk / confirm | [channels/](./channels/index.md) |
| Gateway | sessions, media, cron, approvals | this file + [operations/hosting.md](./operations/hosting.md) |
| Intelligence | models, STT, memory | [intelligence/](./intelligence/index.md) |
| Capabilities | reminders, calendar, book, buy, diet | [capabilities/](./capabilities/index.md) |
| Trust | what may run without you | [trust-and-safety/](./trust-and-safety/index.md) |

## Request lifecycle (WhatsApp audio)

1. Voice note arrives on allowlisted WhatsApp DM
2. Gateway downloads audio and runs **transcription model**
3. Transcript becomes the user turn (optionally echo short transcript)
4. Agent loads hot memory + relevant skills
5. Agent plans with Luna (or escalates model if needed)
6. Safe actions execute immediately (reminders, drafts, reads)
7. Risky actions create an **approval item** → Android/WhatsApp buttons
8. On Accept, skill executes and confirms back on WhatsApp
9. Useful new facts are written into memory

## Session policy

- One primary personal session for DMs
- Call sessions are short-lived and mostly read-only
- Android approvals resume the originating task, not a new personality
- Group chats off by default (security)

## State to persist

- personal memory files / DB
- todos and habit schedules
- pending approvals + expiry
- calendar sync tokens
- skill configs (Booksy prefs, merchants, spend caps)
- audit log of executed side effects

## Failure modes to design for

| Failure | Mitigation |
| --- | --- |
| Bad transcript | show transcript; allow “no, I said…” correction |
| Model refuses / stalls | short retry; ask clarifying question |
| Booking site UI changed | skill fails soft; ask you to confirm manually |
| Approval ignored | expire; remind once; never auto-run |
| Gateway down | queue outbound? or degrade to “I’ll catch up later” on next boot |

## Implementation stance

Prefer OpenClaw primitives (channels, skills, cron, nodes, approvals) over custom microservices. Add custom code only when a skill cannot express the workflow.
