# Production config fragments

Operator-facing OpenClaw merge fragments and env templates. **Harness CI stays on mocks/fixtures** — nothing here is required for `make test-ci`.

## Voice path (PROD-03) — STT + inbound TTS

| File | Purpose |
| --- | --- |
| [`openclaw.voice.json`](./openclaw.voice.json) | Merge fragment: OpenAI STT chain (`gpt-4o-transcribe` → mini) + `messages.tts.auto: inbound` |
| [`openclaw.voice.whisper-fallback.json`](./openclaw.voice.whisper-fallback.json) | Optional Whisper CLI model entry (append after OpenAI models) |
| [`voice.env.example`](./voice.env.example) | `OPENAI_API_KEY` (+ optional TTS fallbacks) — copy to `voice.local.env` |

### Operator quick start (WhatsApp voice)

1. `cp config/production/voice.env.example config/production/voice.local.env` → set `OPENAI_API_KEY`.
2. Deep-merge `openclaw.voice.json` into `~/.openclaw/openclaw.json` (or ensure the same keys exist in [`../openclaw/openclaw.production.json5`](../openclaw/openclaw.production.json5)).
3. Optional: install local `whisper`, append [`openclaw.voice.whisper-fallback.json`](./openclaw.voice.whisper-fallback.json).
4. Reload Gateway → DM voice note → expect `[Audio] <transcript>` and a spoken reply.

| Knob | Value |
| --- | --- |
| STT primary | `openai` / `gpt-4o-transcribe` |
| STT secondary | `openai` / `gpt-4o-mini-transcribe` |
| STT tertiary | Whisper CLI (optional) |
| TTS auto | `inbound` |
| TTS | `openai` / `gpt-4o-mini-tts` / voice `alloy` |

Docs: [`docs/production-voice.md`](../../docs/production-voice.md) · plan: [`agent-plan/intelligence/transcription.md`](../../agent-plan/intelligence/transcription.md) · loader: `src/intelligence/transcription/production.py`

## Other production fragments (sibling PROD tasks)

| File | Task | Purpose |
| --- | --- | --- |
| [`openclaw.voice-call.json`](./openclaw.voice-call.json) | PROD-07 | Twilio/Telnyx voice-call plugin |
| [`voice-call.env.example`](./voice-call.env.example) | PROD-07 | Call provider secrets |
| [`call-mode.policy.json`](./call-mode.policy.json) | PROD-07 | Call-mode tool allowlist |
| [`bookings.json`](./bookings.json) | PROD-08 | Booksy-class browser skill (hard approve; dry-run; `BOOKINGS_LIVE`) |
| [`shopping.json`](./shopping.json) | PROD-08 | Merchant adapters (hard approve; caps; freeze; dry-run; `SHOPPING_LIVE`) |
| [`calendar.json`](./calendar.json) | PROD-06 | Google Calendar (soft confirm; dry-run; `CALENDAR_LIVE`) |
| [`calendar.env.example`](./calendar.env.example) | PROD-06 | Google OAuth secrets template |
| [`openclaw.skills.snippet.json`](./openclaw.skills.snippet.json) | PROD-08 | Bookings + shopping `skills.entries` merge fragment |

Bookings/shopping operator runbook: [`docs/bookings-shopping-production.md`](../../docs/bookings-shopping-production.md). Stub portal / dry-run merchant remain CI-only (`INV-BOOK-*`, `INV-PAY-*`).

Google Calendar runbook: [`docs/calendar-production.md`](../../docs/calendar-production.md). In-memory stub remains CI-only (`INV-APPR-003`).

Full Codex/Luna + WhatsApp allowlist profile: [`../openclaw/`](../openclaw/).
PROD-04 memory/reminders/todos/heartbeat pack: [`../openclaw/skills-production.json5`](../openclaw/skills-production.json5).
