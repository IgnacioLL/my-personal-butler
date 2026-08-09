# OpenClaw production config (Codex / Luna + WhatsApp)

Copy-ready **production** templates for the always-on OpenClaw Gateway.

| File | Purpose |
| --- | --- |
| [`openclaw.production.json5`](./openclaw.production.json5) | Gateway config: Codex auth order, **GPT-5.6 Luna** default, Terra/Sol fallbacks, WhatsApp Web (Baileys) allowlist, media STT hooks, inbound TTS |
| [`escalation.hooks.json`](./escalation.hooks.json) | Intent escalation policy (Luna → Terra/Sol) aligned with `models-and-credits.md` + harness router |
| [`skills-production.json5`](./skills-production.json5) | Optional PROD-04 overlay — enable memory/reminders/todos/heartbeat skills + cron (merge into Gateway config) |

**Not the CI path.** Harness/CI keeps mocks (`config/gateway.harness.json`, `src/harness/whatsapp_transport.py`). Do not wire `test:ci` to these files.

Plan refs: [`channels/whatsapp.md`](../../agent-plan/channels/whatsapp.md), [`models-and-credits.md`](../../agent-plan/intelligence/models-and-credits.md), [`transcription.md`](../../agent-plan/intelligence/transcription.md).

Upstream: [WhatsApp channel](https://docs.openclaw.ai/channels/whatsapp.md), [OpenAI / Codex](https://docs.openclaw.ai/providers/openai/), [Media understanding](https://docs.openclaw.ai/nodes/media-understanding), [TTS](https://docs.openclaw.ai/tools/tts).

---

## Operator checklist (zero → DM)

### 1. Install / start Gateway

Follow the deploy runbook (PROD-01): Docker Compose or `openclaw-gateway.service` on a small always-on VPS. Persist `~/.openclaw` across reboots.

### 2. Install production config

```bash
mkdir -p ~/.openclaw
cp config/openclaw/openclaw.production.json5 ~/.openclaw/openclaw.json
# Edit allowFrom + auth.order.openai placeholders (see below).
```

JSON5 comments are fine in OpenClaw configs; if your installer expects strict JSON, strip comments first.

### 3. Codex / ChatGPT subscription auth

Primary credit path is **Codex / ChatGPT subscription**, not ad-hoc API billing.

```bash
# Interactive (browser callback):
openclaw models auth login --provider openai

# Headless / VPS (device-code flow):
openclaw models auth login --provider openai --device-code

# Confirm profile id, then set auth.order.openai in openclaw.json
openclaw models auth list --provider openai
```

Default model in the template is **`openai/gpt-5.6-luna`** (Luna). Confirm the catalog exposes Luna/Terra/Sol for your account:

```bash
openclaw models list --provider openai
openclaw models set openai/gpt-5.6-luna   # if you need to re-pin after onboard
```

Escalation intent (when to leave Luna) lives in [`escalation.hooks.json`](./escalation.hooks.json). Session override if needed: `/model Terra` or `/model Sol`.

### 4. WhatsApp Web QR login (Baileys)

WhatsApp uses **WhatsApp Web via Baileys** — there is no Twilio WhatsApp messaging channel in the built-in chat registry. Session credentials land under `~/.openclaw` (linked device).

1. Put your E.164 number in `channels.whatsapp.allowFrom` (example placeholder `+15555550100`).
2. Keep:
   - `dmPolicy: "allowlist"` — only `allowFrom` may DM
   - `groupPolicy: "disabled"` — no groups (v1)
   - `selfChatMode: true` — personal-number / self-chat baseline
3. On the Gateway host (or with a reliable path to show the live QR on your phone):

```bash
openclaw channels login --channel whatsapp
```

4. On your phone: **WhatsApp → Settings → Linked Devices → Link a Device** → scan the terminal QR.
5. QR codes expire quickly (~60s). If it times out, re-run the login command.
6. Verify:

```bash
openclaw channels status
```

Remote/headless hosts: deliver the **live** QR to the phone before it expires (SSH with terminal QR rendering, short-lived screenshot, etc.). Do not paste a stale QR image through a slow channel.

Multi-account (optional):

```bash
openclaw channels login --channel whatsapp --account work
```

### 5. Media / STT before agent turn

Production config enables `tools.media.audio` with OpenAI `gpt-4o-transcribe` (mini fallback). WhatsApp voice notes are transcribed **before** the agent reasons; the turn body becomes `[Audio] <transcript>`. STT is **independent** of Luna.

- Empty / garbage transcript → ask to re-speak or send text (do not invent hard-action intent).
- `echoTranscript: true` echoes the transcript for high-stakes clarity.
- TTS reply mode is `messages.tts.auto: "inbound"` (speak back only if you spoke).

Full STT/TTS provider wiring continues in PROD-03; this template already hooks the media path so WhatsApp audio is not a stub.

### 6. Smoke (production only — never in CI)

1. Send yourself a WhatsApp text DM → Luna reply.
2. Send a short voice note → transcript (optional echo) → reply; if inbound TTS is live, expect an audio reply.
3. Confirm a non-allowlisted number cannot talk to the agent.
4. Confirm group messages are ignored (`groupPolicy: "disabled"`).

---

## Security / hygiene

- **Do not commit** filled `allowFrom` with a real number if the repo is public; keep secrets and live numbers in `~/.openclaw` only.
- Never commit OAuth tokens or API keys. Local copies: `config/openclaw/openclaw.local.*` (gitignored).
- Risky actions (money, bookings, self-mod) still require Android hard approve — WhatsApp alone must not execute them.
- Prefer subscription credits; if exhausted, notify rather than silently burning API quota.

---

## Harness vs production

| Concern | Production (`config/openclaw/`) | CI / harness |
| --- | --- | --- |
| Transport | WhatsApp Web (Baileys) | `whatsapp_transport.py` mock |
| Auth | Codex OAuth profile | stubs / no live Luna |
| Models | `openai/gpt-5.6-luna` (+ Terra/Sol) | `src/intelligence/models/router.py` |
| STT | `tools.media.audio` providers | `SttStub` + audio fixtures |
| Config entry | `~/.openclaw/openclaw.json` | `config/gateway.harness.json` |
