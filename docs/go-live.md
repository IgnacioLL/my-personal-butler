# Operator go-live checklist

End-to-end enablement for the always-on personal agent (OpenClaw Gateway + Luna + WhatsApp + Android + voice + calendar + calls + commerce + self-mod). Follow steps **in order** — later capabilities depend on earlier ones.

**Harness CI stays on mocks.** Production paths live under [`config/`](../config/) and [`deploy/`](../deploy/). Never export live flags or production secrets in CI.

**Deploy first:** bring the Gateway up on a cheap VPS before this checklist. See [`deploy.md`](./deploy.md) (Oracle Always Free ARM → Hetzner CX22 fallback).

---

## Quick map

| Step | Capability | PROD | Deep runbook |
| --- | --- | --- | --- |
| 0 | VPS + Gateway | PROD-01 | [`deploy.md`](./deploy.md) |
| 1 | WhatsApp + Luna | PROD-02 | [`config/openclaw/README.md`](../config/openclaw/README.md) |
| 2 | STT + inbound TTS | PROD-03 | [`production-voice.md`](./production-voice.md) |
| 3 | Android control plane | PROD-05 | [`android-pairing.md`](./android-pairing.md) |
| 4 | Google Calendar | PROD-06 | [`calendar-production.md`](./calendar-production.md) |
| 5 | Voice calls | PROD-07 | [`voice-calls.md`](./voice-calls.md) |
| 6 | Bookings + shopping | PROD-08 | [`bookings-shopping-production.md`](./bookings-shopping-production.md) |
| 7 | Self-mod (this repo) | PROD-09 | [`config/selfmod.production.json`](../config/selfmod.production.json) |

Skills pack (memory, reminders, todos, heartbeat) is enabled with PROD-02/04 — merge [`config/openclaw/skills-production.json5`](../config/openclaw/skills-production.json5) when seeding Gateway config.

---

## 0. Gateway on a cheap VPS (prerequisite)

- [ ] Provision **Oracle Cloud Always Free ARM** (Ampere A1) if available in your region; else **Hetzner CX22-class** (~€4–5/mo). See [`deploy.md` § Provision](./deploy.md#1-provision-the-vm).
- [ ] Clone repo, run Docker Compose or systemd path; persist `~/.openclaw` across reboots.
- [ ] Generate `OPENCLAW_GATEWAY_TOKEN`; access Control UI via SSH tunnel (port 18789 loopback).
- [ ] Schedule daily backup (`deploy/backup-openclaw.sh`).

**Artifacts:** [`deploy/docker-compose.yml`](../deploy/docker-compose.yml), [`deploy/.env.example`](../deploy/.env.example), [`deploy/setup-docker.sh`](../deploy/setup-docker.sh).

---

## 1. WhatsApp + Codex / Luna (PROD-02)

WhatsApp is the primary conversation channel. Luna runs on your **Codex / ChatGPT subscription** — not metered API chat.

### Config

- [ ] Copy [`config/openclaw/openclaw.production.json5`](../config/openclaw/openclaw.production.json5) → `~/.openclaw/openclaw.json`.
- [ ] Set `channels.whatsapp.allowFrom` to your E.164 number (placeholder in template: `+15555550100`).
- [ ] Keep `dmPolicy: allowlist`, `groupPolicy: disabled`, `selfChatMode: true`.
- [ ] Merge [`config/openclaw/skills-production.json5`](../config/openclaw/skills-production.json5) for memory / reminders / todos / heartbeat.
- [ ] Optional: merge [`config/openclaw/escalation.hooks.json`](../config/openclaw/escalation.hooks.json) for Luna → Terra/Sol routing.

### Auth (subscription — not API key)

```bash
openclaw models auth login --provider openai          # or --device-code on headless VPS
openclaw models auth list --provider openai
openclaw models set openai/gpt-5.6-luna
```

### WhatsApp Web QR

```bash
openclaw channels login --channel whatsapp
openclaw channels status
```

### Smoke

- [ ] Text DM from allowlisted number → Luna reply.
- [ ] Non-allowlisted number cannot DM.
- [ ] Group messages ignored.

**Config refs:** [`config/openclaw/`](../config/openclaw/) · plan: [`agent-plan/channels/whatsapp.md`](../agent-plan/channels/whatsapp.md).

---

## 2. STT + inbound TTS (PROD-03)

Voice notes on WhatsApp need an **OpenAI API key** for transcription and spoken replies. Luna chat credits (Codex subscription) do **not** cover STT/TTS.

### Config

- [ ] `cp config/production/voice.env.example config/production/voice.local.env` → set `OPENAI_API_KEY`.
- [ ] Deep-merge [`config/production/openclaw.voice.json`](../config/production/openclaw.voice.json) into `~/.openclaw/openclaw.json` (do not overwrite WhatsApp / Luna sections from step 1).
- [ ] Wire `voice.local.env` via Docker `env_file` or systemd `EnvironmentFile`.
- [ ] Optional resilience: install local `whisper` CLI, append [`config/production/openclaw.voice.whisper-fallback.json`](../config/production/openclaw.voice.whisper-fallback.json).

### Smoke

- [ ] Send a short voice note → `[Audio] <transcript>` in the turn → spoken reply (inbound TTS).
- [ ] Text DM still returns text-only (no auto TTS).

**Config refs:** [`config/production/openclaw.voice.json`](../config/production/openclaw.voice.json), [`config/production/voice.env.example`](../config/production/voice.env.example).

---

## 3. Android companion (PROD-05)

Android is the **control plane**: todos, hard approvals (Accept / Deny / Edit), kill switches, self-mod cards. WhatsApp stays conversation-only for risky actions.

### Config

- [ ] Merge [`config/android.example.yaml`](../config/android.example.yaml) into live Gateway profile (`channels.android.enabled: true`, todos + approvals + status + self-mod cards).
- [ ] Ensure `skills.load.extraDirs` includes this repo's `src/skills/`.

### Pair phone

- [ ] Install OpenClaw Android from Play Store or a signed release APK.
- [ ] Gateway reachable via LAN `ws://` or Tailscale Serve `wss://` (not raw tailnet `ws://` for first pairing).
- [ ] `openclaw devices list` → `openclaw devices approve <requestId>`.
- [ ] `openclaw nodes approve <requestId>` if node capability is pending.

### Smoke (required before calendar / commerce / self-mod)

Run the checklist in [`android-pairing.md` § Operator checklist](./android-pairing.md#operator-checklist-go-live-smoke):

- [ ] Todo sync WhatsApp ↔ Android.
- [ ] Hard-action proposal → Inbox card → Deny blocks execute.
- [ ] Accept once → single execute; freeze spending / freeze self-mod / cancel pending work.

**Config refs:** [`config/android.example.yaml`](../config/android.example.yaml) · CI doubles stay in [`config/android.harness.json`](../config/android.harness.json).

---

## 4. Google Calendar (PROD-06)

Soft-confirm writes: propose → Accept → one execute. Dry-run by default.

### Secrets (Google Cloud — free tier API; no purchase)

- [ ] Google Cloud Console → enable **Google Calendar API** → OAuth client (Desktop).
- [ ] Complete offline consent once; obtain `refresh_token`.
- [ ] `cp config/production/calendar.env.example config/production/calendar.local.env`
- [ ] Fill `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, `GOOGLE_CALENDAR_REFRESH_TOKEN`.
- [ ] Set `CALENDAR_MODE=google`; keep `CALENDAR_LIVE` **unset** initially.

### Config

- [ ] Point `CALENDAR_PROFILE` at [`config/production/calendar.json`](../config/production/calendar.json) (`"live": false` in JSON).
- [ ] Load skill from [`src/skills/calendar/`](../src/skills/calendar/).

### Smoke

- [ ] Propose `calendar_create` from WhatsApp → Android soft-confirm → dry-run (no Google write).
- [ ] When satisfied: set `CALENDAR_LIVE=1` (or `"live": true` in production JSON) → Accept → one real event.

**Config refs:** [`config/production/calendar.json`](../config/production/calendar.json), [`config/production/calendar.env.example`](../config/production/calendar.env.example).

---

## 5. Voice calls (PROD-07)

Outbound calls to **operator handset only**. Requires public HTTPS webhook (plan during PROD-01 deploy).

### Purchase vs subscription

| Item | Type | Notes |
| --- | --- | --- |
| Twilio or Telnyx account | Sign-up (pay-as-you-go) | Per-minute + per-number fees |
| Dedicated phone number | **Purchase** | E.164 for `fromNumber` |
| OpenClaw `@openclaw/voice-call` plugin | Free install | `openclaw plugins install @openclaw/voice-call` |

### Secrets

- [ ] `cp config/production/voice-call.env.example config/production/voice-call.local.env`
- [ ] Fill `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` (or Telnyx equivalents).
- [ ] Set `VOICE_CALL_FROM_NUMBER`, `VOICE_CALL_TO_NUMBER`, `VOICE_CALL_OUTBOUND_ALLOWLIST`.
- [ ] Set `VOICE_CALL_PUBLIC_URL` to `https://your-domain/voice/webhook` (see [`deploy.md` § HTTPS](./deploy.md#https-and-twilio-webhooks-later)).

### Config

- [ ] Merge [`config/production/openclaw.voice-call.json`](../config/production/openclaw.voice-call.json).
- [ ] Load [`config/production/call-mode.policy.json`](../config/production/call-mode.policy.json) — **INV-APPR-005** blocks buy / book / self-mod mid-call.

### Smoke

- [ ] `openclaw voicecall smoke --to "+YOUR_OPERATOR"` (dry-run) then `--yes` for short live notify.
- [ ] After-call WhatsApp summary arrives (`kind=after_call_summary`).

**Config refs:** [`config/production/openclaw.voice-call.json`](../config/production/openclaw.voice-call.json), [`config/production/voice-call.env.example`](../config/production/voice-call.env.example).

---

## 6. Bookings + shopping (PROD-08)

**Hard approve** + **dry-run default**. Real money / external reservations only after Android UX is proven.

### Config (no secrets in git)

- [ ] Merge [`config/production/openclaw.skills.snippet.json`](../config/production/openclaw.skills.snippet.json); keep skills `enabled: false` until ready.
- [ ] Edit [`config/production/bookings.json`](../config/production/bookings.json) — replace `REPLACE_*` shop URLs; `"mode": "dry_run"`.
- [ ] Edit [`config/production/shopping.json`](../config/production/shopping.json) — merchant URLs; caps (default daily 50 / weekly 150); `"mode": "dry_run"`.
- [ ] Use separate browser profile for bookings (`browser.profile_name: bookings`).

### Live flags (both required)

| Skill | Config | Env |
| --- | --- | --- |
| Bookings | `"mode": "live"` | `BOOKINGS_LIVE=1` |
| Shopping | `"mode": "live"` | `SHOPPING_LIVE=1` |

Either alone stays dry-run. **Never** set live flags under `CI=1` / `make test-ci`.

### Smoke

- [ ] Propose book/buy → Android hard-approve card → dry-run execute (no external side effect).
- [ ] Deny / freeze spending / cap breach blocks execute (`INV-BOOK-*`, `INV-PAY-*`).
- [ ] Only when intentional: flip live flags + Accept → one real reservation or charge.

**Config refs:** [`config/production/bookings.json`](../config/production/bookings.json), [`config/production/shopping.json`](../config/production/shopping.json).

---

## 7. Self-modification (PROD-09)

Agent may propose code/docs/config changes **in this repo** on allowlisted paths only. Hard approve + freeze self-mod.

### Config

- [ ] Load [`config/selfmod.production.json`](../config/selfmod.production.json) and [`config/selfmod.allowlist.production.json`](../config/selfmod.allowlist.production.json).
- [ ] Skill: [`src/skills/self-modification/SKILL.md`](../src/skills/self-modification/SKILL.md) via `skills.load.extraDirs`.
- [ ] Branch prefix `cursor/agent-self-*`; never apply directly to `main`.

### Allowlist (summary)

| Allowed | Denied |
| --- | --- |
| `src/skills/**`, `docs/**`, `config/**`, `src/policy/**` | `.env`, `*.local.*`, `data/**`, secrets paths |

### Smoke

- [ ] Propose trivial doc edit → Android card shows diff, files, rollback ref.
- [ ] Accept once → apply on feature branch; second apply blocked.
- [ ] Status → **Freeze self-mod** → Accept refuses apply.
- [ ] Policy-change subtype (`src/policy/**`) shows louder badge.

**CI uses fixtures only** — never point INV-SELF at the live checkout.

---

## Secrets inventory

Placeholders only. Copy `*.env.example` → `*.local.env` (gitignored). Never commit filled values.

| Secret / credential | Template | Subscription vs purchase | Used by |
| --- | --- | --- | --- |
| `OPENCLAW_GATEWAY_TOKEN` | [`deploy/.env.example`](../deploy/.env.example) | Generate (free) | Gateway Control UI auth |
| Codex / ChatGPT OAuth profile | onboard CLI | **Subscription** (ChatGPT/Codex plan) | Luna chat, escalation |
| `OPENAI_API_KEY` | [`config/production/voice.env.example`](../config/production/voice.env.example) | **API pay-as-you-go** (metered) | STT (`gpt-4o-transcribe`) + TTS (`gpt-4o-mini-tts`) |
| WhatsApp session | `openclaw channels login` | Free (linked device) | Baileys transport — no Twilio for chat |
| Google OAuth client + refresh token | [`config/production/calendar.env.example`](../config/production/calendar.env.example) | **Free** GCP project + API quota | Calendar writes |
| `TWILIO_*` or `TELNYX_*` | [`config/production/voice-call.env.example`](../config/production/voice-call.env.example) | Account + **purchased number** + usage | Outbound voice calls only |
| Booksy / merchant logins | operator browser profile | Existing accounts (no template) | Bookings / shopping browsers |
| Optional TTS fallbacks | `voice.env.example` | API if enabled | ElevenLabs / MiniMax |

**Not secrets (versioned config):** everything under [`config/openclaw/`](../config/openclaw/), [`config/production/*.json`](../config/production/), [`config/selfmod.*.production.json`](../config/).

---

## Cost expectations (personal use, order-of-magnitude)

| Line item | Typical cost | Notes |
| --- | --- | --- |
| VPS (Oracle Free ARM) | **$0/mo** | If capacity available in region |
| VPS (Hetzner CX22) | **~€4–5/mo** | Fallback always-on host |
| Codex / ChatGPT (Luna) | **Existing subscription** | Primary chat credit path — not per-token API for Luna |
| OpenAI API (STT + TTS) | **~$1–10/mo** light voice use | `gpt-4o-transcribe` + `gpt-4o-mini-tts`; scales with voice-note volume |
| Twilio / Telnyx number | **~$1–2/mo** + per-minute | Only if voice calls enabled |
| Google Calendar API | **$0** | Within free quota for personal calendars |
| Bookings / shopping | **$0 infra** | Real spend is reservations and merchant charges you approve |
| Domain + TLS (optional) | **~$10–15/yr** | Needed for stable voice webhooks; tunnel OK for bring-up |

**Cheapest full path:** Oracle Free VPS + existing Codex subscription + light OpenAI API for voice. Add Twilio only when calls matter.

---

## Production config index

All operator merge fragments and env templates:

```
config/
├── openclaw/                    # PROD-02 + PROD-04
│   ├── openclaw.production.json5
│   ├── skills-production.json5
│   └── escalation.hooks.json
├── production/                  # PROD-03, 06, 07, 08
│   ├── openclaw.voice.json
│   ├── voice.env.example
│   ├── calendar.json + calendar.env.example
│   ├── openclaw.voice-call.json + voice-call.env.example
│   ├── call-mode.policy.json
│   ├── bookings.json + shopping.json
│   └── openclaw.skills.snippet.json
├── android.example.yaml         # PROD-05
├── selfmod.production.json      # PROD-09
└── selfmod.allowlist.production.json
```

Deploy + persistence: [`deploy/`](../deploy/) · operator runbook: [`deploy.md`](./deploy.md).

---

## Final go-live smoke (all layers)

Run once after step 7 (or after the highest layer you enable):

1. [ ] Gateway survives reboot; WhatsApp reconnects.
2. [ ] Voice note round-trip (STT + inbound TTS).
3. [ ] Android paired; todo + hard-approve flows pass ([`android-pairing.md`](./android-pairing.md)).
4. [ ] Calendar dry-run propose → Accept (then `CALENDAR_LIVE` when ready).
5. [ ] Optional: one voice-call smoke to operator number.
6. [ ] Book/buy dry-run hard approve; live flags stay off until deliberate.
7. [ ] Self-mod propose on allowlisted path → Accept on branch; freeze self-mod blocks apply.
8. [ ] Daily backup cron firing; `openclaw doctor` clean.

```bash
make test-ci              # operator laptop / CI — must stay green
make test-ci-fail-closed  # invariants fail closed when broken
```

---

## Related docs

- [`deploy.md`](./deploy.md) — VPS provisioning, Docker/systemd, backup, HTTPS for webhooks
- [`config/README.md`](../config/README.md) — config layout and harness vs production
- [`config/production/README.md`](../config/production/README.md) — merge fragments quick reference
- [`status.md`](../status.md) — PROD wave tracker
