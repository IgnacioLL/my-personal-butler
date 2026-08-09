# Voice calls — production runbook (PROD-07)

Full outbound call path for the always-on OpenClaw Gateway. Harness CI keeps
`MockVoiceProvider` — never place live Twilio/Telnyx calls from `test:ci`.

## What you get

1. Provider credentials / env templates
2. Public webhook URL notes
3. Outbound allowlist → operator handset only
4. Call-mode tool allowlist (`INV-APPR-005`) — no buy / book / self-mod-apply mid-call
5. After-call WhatsApp summary

Plan leaf: [`agent-plan/channels/voice-calls.md`](../agent-plan/channels/voice-calls.md).

## Files

| Path | Role |
| --- | --- |
| [`config/production/voice-call.env.example`](../config/production/voice-call.env.example) | Secrets + webhook env template |
| [`config/production/openclaw.voice-call.json`](../config/production/openclaw.voice-call.json) | OpenClaw `@openclaw/voice-call` merge fragment |
| [`config/production/call-mode.policy.json`](../config/production/call-mode.policy.json) | Production INV-APPR-005 policy |
| [`src/skills/voice-calls/`](../src/skills/voice-calls/) | Skill + `policy.json` Gateway can load |
| [`src/channels/voice/config.py`](../src/channels/voice/config.py) | Config loader / outbound allowlist |
| [`src/channels/voice/production.py`](../src/channels/voice/production.py) | Production provider (mock-backed in CI) |
| [`src/policy/call_mode.py`](../src/policy/call_mode.py) | Shared call-mode gate helpers |

## Operator checklist

### 1. Install plugin on the Gateway host

```bash
openclaw plugins install @openclaw/voice-call
# restart Gateway so the plugin loads
```

### 2. Copy secrets template

```bash
cp config/production/voice-call.env.example config/production/voice-call.local.env
# fill TWILIO_* or TELNYX_* + VOICE_CALL_FROM_NUMBER / VOICE_CALL_TO_NUMBER
```

Never commit `*.local.env`.

### 3. Merge plugin config

Merge [`openclaw.voice-call.json`](../config/production/openclaw.voice-call.json) into
`~/.openclaw/openclaw.json` under `plugins.entries.voice-call`. Replace placeholder
numbers with your dedicated Twilio/Telnyx number (`fromNumber`) and operator
handset (`toNumber`). Prefer SecretRefs / env for tokens — do not paste live
secrets into git-tracked JSON.

### 4. Public webhook URL

Twilio and Telnyx **require** a publicly reachable HTTPS webhook:

- Prefer the Gateway VPS `public_url` + path `/voice/webhook`
  (see `config/gateway.example.yaml` `hosting.public_url`).
- Set `VOICE_CALL_PUBLIC_URL` / `plugins.entries.voice-call.config.publicUrl` to the
  full URL, e.g. `https://gateway.example.com/voice/webhook`.
- Local tunnels (ngrok / Tailscale Funnel) are fine for bring-up; keep
  `skipSignatureVerification: false` in production.
- Webhook serve defaults: port `3334`, path `/voice/webhook`.

Validate:

```bash
openclaw voicecall setup
openclaw voicecall smoke --to "+YOUR_OPERATOR"   # dry-run
openclaw voicecall smoke --to "+YOUR_OPERATOR" --yes  # short live notify
```

### 5. Outbound allowlist

Only the operator number may be dialed in v1:

- Env: `VOICE_CALL_OUTBOUND_ALLOWLIST=+E.164`
- Fragment: `personalButler.voiceCalls.outboundAllowlist`
- Python gate: `VoiceCallConfig.outbound_allowed` / `ProductionVoiceProvider.place_call`

Inbound stays `inboundPolicy: disabled` until explicitly designed.

### 6. Call-mode policy (`INV-APPR-005`)

Mid-call tools are limited to reads (`calendar_read`, `memory_read`, `todo_read`,
`source_read`). `buy`, `book`, and `self_mod_apply` return
`call_mode_forbidden_hard_action`. Mutating intents become post-call approvals
or tasks. Policy sources must stay in sync:

- `src/skills/voice-calls/policy.json`
- `config/production/call-mode.policy.json`
- `src/channels/voice/allowlist.py`

### 7. After-call WhatsApp summary

On hangup, queue a WhatsApp DM with `kind=after_call_summary` (script topic +
outcome + call id). Enabled by default via
`personalButler.voiceCalls.afterCallWhatsAppSummary` and
`MockVoiceProvider` / `ProductionVoiceProvider.end_call`.

## CI vs production

| Mode | Provider | Network |
| --- | --- | --- |
| `make test-ci` | `mock` (`MockVoiceProvider`) | none |
| Production Gateway | `twilio` or `telnyx` via OpenClaw plugin | carrier + public webhook |

Set `VOICE_CALL_PROVIDER=mock` for local dry-runs without credentials.

## Safety reminders

- Quiet hours still apply unless the reminder is marked emergency
- Cap call frequency (`maxCallsPerHour` in fragment) to avoid spam loops
- Never enable `skipSignatureVerification` on a public endpoint
- No purchase / booking / self-mod apply during a live call
