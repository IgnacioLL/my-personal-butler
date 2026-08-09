# Production voice path (STT + TTS)

Operator runbook for the always-on WhatsApp voice path. Harness CI continues to use fixture STT (`SttStub`); nothing here is required for `make test-ci`.

Aligns with [`agent-plan/intelligence/transcription.md`](../agent-plan/intelligence/transcription.md) and OpenClaw Gateway media + TTS config.

## Pipeline

```text
WhatsApp OGG voice note (DM allowlist)
  → tools.media.audio (OpenAI gpt-4o-transcribe → mini → optional Whisper CLI)
  → "[Audio] <transcript>" user turn
  → Luna (default chat model — independent of STT)
  → messages.tts.auto = inbound → spoken WhatsApp reply
```

## Config fragments

| Path | Role |
| --- | --- |
| [`config/production/openclaw.voice.json`](../config/production/openclaw.voice.json) | Primary merge fragment |
| [`config/production/openclaw.voice.whisper-fallback.json`](../config/production/openclaw.voice.whisper-fallback.json) | Optional Whisper CLI model entry |
| [`config/production/voice.env.example`](../config/production/voice.env.example) | Secrets template |

Merge `tools` + `messages` from `openclaw.voice.json` into `~/.openclaw/openclaw.json` (or the compose-mounted config). Do not replace the whole file if PROD-02 already seeded Codex / WhatsApp allowlist sections.

## Secrets

```bash
cp config/production/voice.env.example config/production/voice.local.env
# edit OPENAI_API_KEY=sk-...
```

| Variable | Required | Used by |
| --- | --- | --- |
| `OPENAI_API_KEY` | yes (production) | STT models + OpenAI TTS |
| `OPENAI_TTS_BASE_URL` | no | Compatible TTS endpoint override |
| `ELEVENLABS_API_KEY` / `XI_API_KEY` | no | Optional TTS fallback |
| `MINIMAX_API_KEY` | no | Optional TTS fallback |

Never commit `voice.local.env`. Wire it via Docker `env_file` or systemd `EnvironmentFile`.

## STT model chain

1. **Primary:** `gpt-4o-transcribe` — best accuracy for short WhatsApp notes.
2. **Secondary:** `gpt-4o-mini-transcribe` — tried next if primary fails/skips (size/timeout).
3. **Optional Whisper CLI:** append the model object from `openclaw.voice.whisper-fallback.json` after the OpenAI entries.

### Whisper CLI fallback

OpenClaw walks `tools.media.audio.models` in order. To add a local Whisper binary:

1. Install `whisper` on the Gateway host (operator action — agents do not install packages).
2. Deep-merge / append the CLI model entry so it is **after** the OpenAI models.
3. Ensure `whisper` is on `PATH` (or set `command` to an absolute path).
4. Reload Gateway and send a test voice note with OpenAI keys temporarily unset to confirm fallback.

Whisper is a resilience path, not the default — prefer OpenAI transcription for latency and language quality.

## TTS inbound mode

Production sets `messages.tts.auto` to **`inbound`**:

- Inbound voice note → agent may attach a spoken reply.
- Inbound text → text reply only (no auto TTS).

Override per session with `/tts off|on` if needed; keep the config default at `inbound` for v1.

OpenAI TTS defaults: model `gpt-4o-mini-tts`, voice `alloy` (Opus voice notes on WhatsApp).

## Bounds and DM scope

- `maxBytes`: 20 MiB (OpenClaw default-class bound).
- `timeoutSeconds`: 120 for the audio understanding pass.
- Scope: allow `chatType: direct` only — refuse group audio (groups remain disabled in channel policy).

## Failure UX (product)

| Case | Behavior |
| --- | --- |
| Empty / garbage transcript | Ask for a short re-speak or text |
| Ambiguous hard action (“buy…”) | Echo transcript + confirm before proposing |
| STT provider outage | Next model in chain; then clarification — never silent hard actions |

## CI vs production

| Mode | STT | TTS |
| --- | --- | --- |
| `make test-ci` | `SttStub` + `fixtures/audio/manifest.json` | `TtsPolicySpy` (mode rules only) |
| Production Gateway | OpenAI (+ optional Whisper) via `openclaw.voice.json` | OpenAI TTS, `auto: inbound` |

Do **not** point harness profiles at live STT. Structural validation of production fragments lives in `src/intelligence/transcription/production.py` and unit checks under `unit.prod03.*`.

## Verify after deploy

1. Gateway up with `OPENAI_API_KEY` loaded.
2. From the allowlisted WhatsApp DM, send a short voice note.
3. Confirm outbound includes a transcript-backed reply and a voice note when TTS succeeds.
4. Send a text-only message — confirm no auto voice reply.
