# Intelligence

How the agent thinks, hears, and remembers.

## Documents

- [Models and credits](./models-and-credits.md) — Luna default, Codex subscription, escalation
- [Transcription](./transcription.md) — mandatory STT path for WhatsApp audio
- [Memory](./memory.md) — personal knowledge the agent uses to plan for you

## Design summary

```text
Audio  →  STT model  →  transcript
Text/transcript  →  Luna (default) / Sol (hard)  →  tool calls
                          ↓
                     Memory read/write
```

## Principles

1. Transcription is infrastructure, not optional
2. Luna handles most daily turns to preserve Codex allowance
3. Memory is curated facts + searchable history, not an unbounded dump
4. The agent should write back useful preferences without being asked every time
