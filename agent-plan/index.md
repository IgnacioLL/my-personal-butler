# Personal Agent — System Plan

Top-level plan for a general-purpose personal agent: WhatsApp-first, voice-capable, memory-aware, and able to act in the real world under explicit approvals.

## Decision snapshot

| Choice | Decision |
| --- | --- |
| Runtime | **OpenClaw** (Gateway + skills + channels) |
| Why not Hermes | Hermes wins on self-improving memory; OpenClaw wins on WhatsApp, calls, Android approvals, Codex/Luna |
| Main channel | WhatsApp (text + audio) |
| Secondary channels | Phone calls (outbound reminders / talk), Android companion |
| Default model | GPT-5.6 **Luna** via Codex subscription |
| Escalation model | Terra/Sol for hard multi-step planning |
| Always-on infra | Dedicated transcription model for WhatsApp audios |

## Document map

```text
agent-plan/
├── index.md                          ← you are here
├── vision-and-goals.md               ← what “perfect” means
├── architecture.md                   ← system shape and data flow
├── platform-choice.md                ← OpenClaw vs Hermes
├── channels/
│   ├── index.md
│   ├── whatsapp.md
│   ├── voice-calls.md
│   └── android-companion.md
├── intelligence/
│   ├── index.md
│   ├── models-and-credits.md
│   ├── transcription.md
│   └── memory.md
├── capabilities/
│   ├── index.md
│   ├── reminders-and-habits.md
│   ├── calendar.md
│   ├── todos.md
│   ├── bookings.md
│   ├── shopping.md
│   ├── diet-and-planning.md
│   └── self-modification.md
├── trust-and-safety/
│   ├── index.md
│   └── approval-matrix.md
├── operations/
│   ├── index.md
│   ├── hosting.md
│   └── roadmap.md
└── testing/
    ├── index.md                  ← how we prove it works (AI-autonomous)
    ├── strategy.md
    ├── test-levels.md
    ├── component-matrix.md
    ├── harnesses-and-fixtures.md
    ├── safety-invariants.md
    ├── e2e-flows.md
    ├── autonomous-agent-process.md
    ├── ci-gates.md
    ├── roadmap.md
    └── components/
```

## Read order

1. [Vision and goals](./vision-and-goals.md)
2. [Platform choice](./platform-choice.md)
3. [Architecture](./architecture.md)
4. Channels → Intelligence → Capabilities → Trust → Operations
5. [Testing](./testing/index.md) — verification strategy before implementation

## Design principles

1. **One brain, many surfaces** — WhatsApp, Android, and calls share memory and policy.
2. **Propose → Approve → Execute** for money, external side effects, and any self-modification of source.
3. **Voice is first-class** — audio in must be transcribed; audio out when appropriate.
4. **Proactive but quiet** — useful nudges, not chatter.
5. **Ship thin vertical slices** — reminders + memory before Booksy, shopping, and self-mod.
6. **Self-mod is allowed but caged** — the agent may edit its own repo only via hard-approved diffs on allowlisted paths.
7. **Autonomous verification** — prefer harnesses, mocks, and invariants an AI can run without human review.

## Status

Planning only. No implementation yet.
