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

## Model guidance

Use a dedicated transcription-capable model/provider (examples to evaluate at implementation time):

- OpenAI transcription models (`gpt-4o-transcribe` / mini variant)
- Whisper API or local Whisper fallback
- Alternatives (Deepgram, etc.) if latency/cost wins

Do **not** rely on Luna alone as the STT system unless OpenClaw’s media path proves it is first-class and reliable for your language.

## UX around errors

| Case | Behavior |
| --- | --- |
| Empty / garbage transcript | ask for a short re-speak or text |
| Ambiguous critical request (“buy…”) | echo transcript + ask confirm before proposing purchase |
| User corrects transcript | overwrite understanding; don’t argue |

## Calls

Call audio may use realtime transcription from the voice-call provider path. Still separate from the main chat model policy.

## Acceptance criteria

- [ ] 100% of WhatsApp voice notes pass through STT
- [ ] Transcript available to the agent turn
- [ ] Failure path asks for clarification instead of hallucinating intent
- [ ] Optional transcript echo for high-stakes commands
