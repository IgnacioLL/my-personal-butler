# Transcription

## Why this is mandatory

The main interface is WhatsApp audio (and later calls). If transcription is weak, the whole agent feels broken — even if Luna is smart.

Treat STT as a **permanent infrastructure dependency**, not a nice-to-have.

## Requirements

- Transcribe every inbound WhatsApp voice note before the agent reasons
- Support your spoken language(s) reliably
- Bound max audio size / duration
- Prefer low latency for short notes
- Keep an auditable transcript attached to the turn

## Proposed pipeline

```text
WhatsApp OGG voice note
  → Gateway media pipeline
  → STT provider/model
  → "[Audio] <transcript>" as user message
  → Agent (Luna)
  → optional TTS reply if inbound was audio
```

## Model guidance (production)

Use a **dedicated** transcription provider — independent from Luna / Codex chat:

| Priority | Provider | Model | Notes |
| --- | --- | --- | --- |
| 1 (primary) | OpenAI | `gpt-4o-transcribe` | Best accuracy for short WhatsApp notes |
| 2 (fallback) | OpenAI | `gpt-4o-mini-transcribe` | Next in OpenClaw `tools.media.audio.models` chain |
| 3 (optional) | Whisper CLI | local `whisper` binary | Offline / API-outage resilience |

**TTS (WhatsApp replies):** OpenAI `gpt-4o-mini-tts` with `messages.tts.auto: inbound` — speak back only when the user sent audio.

Copy-ready OpenClaw fragments + env template:

- [`config/production/openclaw.voice.json`](../../config/production/openclaw.voice.json)
- [`config/production/voice.env.example`](../../config/production/voice.env.example)
- Operator runbook: [`docs/production-voice.md`](../../docs/production-voice.md)

Do **not** rely on Luna alone as the STT system unless OpenClaw’s media path proves it is first-class and reliable for your language.

### Harness / CI

CI keeps the fixture STT path (`SttStub` + `fixtures/audio/`). Production providers are additive — never required for `make test-ci`. Default `STT_PROVIDER` resolves to `fixture`.

## UX around errors

| Case | Behavior |
| --- | --- |
| Empty / garbage transcript | ask for a short re-speak or text |
| Ambiguous critical request (“buy…”) | echo transcript + ask confirm before proposing purchase |
| User corrects transcript | overwrite understanding; don’t argue |

## Calls

Call audio may use realtime transcription from the voice-call provider path. Still separate from the main chat model policy.

## Acceptance criteria

- [x] 100% of WhatsApp voice notes pass through STT (harness: INV-INGRESS-003; production: `tools.media.audio.enabled`)
- [x] Transcript available to the agent turn (`[Audio] <transcript>`)
- [x] Failure path asks for clarification instead of hallucinating intent
- [x] Optional transcript echo for high-stakes commands
- [x] Production STT/TTS config wired (`config/production/`) with inbound TTS
