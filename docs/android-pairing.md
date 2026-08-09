# Android companion — production pairing runbook

Pair the official **OpenClaw Android** node to your always-on Gateway so the phone is the control plane for todos, hard approvals (Accept / Deny / Edit), kill switches, and self-mod cards.

WhatsApp stays conversation. Android stays lists + approvals + status.

Upstream references: [OpenClaw Android](https://docs.openclaw.ai/platforms/android), [Nodes](https://docs.openclaw.ai/nodes), [Device pairing](https://docs.openclaw.ai/gateway/pairing).

This repo’s product shape: [`agent-plan/channels/android-companion.md`](../agent-plan/channels/android-companion.md).  
Config templates: [`config/android.example.yaml`](../config/android.example.yaml) (production) · [`config/android.harness.json`](../config/android.harness.json) (CI doubles).

## Prerequisites

- Gateway already up on VPS/home (see deploy docs / [`agent-plan/operations/hosting.md`](../agent-plan/operations/hosting.md)).
- `openclaw` CLI on the Gateway host (or via SSH).
- Phone on the same LAN **or** same Tailscale tailnet with a **`wss://`** endpoint (Tailscale Serve / Funnel or other TLS). Do **not** use raw tailnet `ws://` for first-time mobile pairing.
- Android app from [Google Play](https://play.google.com/store/apps/details?id=ai.openclaw.app) or a signed `OpenClaw-Android.apk` from a supported [GitHub Release](https://github.com/openclaw/openclaw/releases).
- Production fragment merged into Gateway config from `config/android.example.yaml` (copy keys into `gateway.local.yaml` / `~/.openclaw` — never commit secrets).

## Pair phone → Gateway

### 1. Start / confirm Gateway

```bash
openclaw gateway --port 18789 --verbose
# Prefer for remote phone:
openclaw gateway --tailscale serve
```

Confirm logs show a listening WebSocket (LAN `ws://` or Serve `wss://`).

### 2. Enable Android control plane in config

Merge [`config/android.example.yaml`](../config/android.example.yaml) into the live Gateway profile:

- `channels.android.enabled: true`
- todos sync + approval inbox + status/kill switches + self-mod cards on
- hard approvals prefer Android; WhatsApp remains backup soft-confirm surface

Reload/restart Gateway after edit.

### 3. Connect from Android

1. Open **OpenClaw** → **Connect**.
2. Prefer **Setup Code** (`openclaw qr` on the host, or Control UI). For limited/plaintext LAN, note Full vs Limited access in **Settings → Gateway**.
3. If discovery fails: **Manual** / Advanced — host + port. Private LAN may use `ws://`; Tailscale/public **must** use `wss://` / Serve.
4. Keep the app’s foreground service notification so the node stays reachable.

### 4. Approve device pairing (Gateway host)

```bash
openclaw devices list
openclaw devices approve <requestId>
# or reject:
openclaw devices reject <requestId>
```

### 5. Approve node capability surface (if prompted)

Newer Gateways require **node** pairing in addition to device pairing before declared node commands are live:

```bash
openclaw nodes status
openclaw nodes pending    # if available on your CLI version
openclaw nodes approve <requestId>
```

Confirm `openclaw nodes status` shows the phone **paired + connected**.

### 6. Optional: auto-approve only on a locked subnet

`gateway.nodes.pairing` / CIDR allowlists (see upstream Android docs) may auto-approve **fresh** `role: node` with no scopes. Leave this **off** unless the phone always joins from a tightly controlled network. Role/scope/key changes still need manual approval.

## Control plane screens (production)

| Screen | Purpose | Config keys (`android.example.yaml`) |
| --- | --- | --- |
| **Todos** | Open tasks; complete marks done in Gateway store | `features.todos` |
| **Inbox / Approvals** | Pending soft/hard items; **Accept** / **Deny** / **Edit** | `features.approvals` |
| **Status** | Gateway online, pause agent, freeze spending, freeze self-mod, cancel pending | `features.status` / `kill_switches` |
| **Self-mod cards** | Diff summary, files touched, rollback ref; **Code change** / **policy-change** badge | `features.self_mod_cards` |

Canonical state lives on the Gateway. Android renders and acknowledges. CI keeps API doubles under `src/channels/android/` (`config/android.harness.json`) — no live device in `make test-ci`.

### Approval UX (must show)

- Plain-language summary + why (source utterance / channel)
- Cost / merchant / time when relevant
- Expiry (“auto-cancels in …”)
- Self-mod: `diff_summary`, `files_touched`, `rollback_ref`
- Policy-change subtype louder than ordinary code change
- Actions: **Accept once** · **Deny** · **Edit** details (then Accept/Deny)

Denied / expired / cancelled never execute (`INV-APPR-*`).

### Kill switches (Status)

| Switch | Effect |
| --- | --- |
| Pause agent | No proactive cron/heartbeat work |
| Freeze spending | Blocks `buy` execute (including stale accepted) |
| Freeze self-mod | Blocks `self_mod_apply` / `policy_change` execute |
| Cancel pending | All pending approvals → cancelled |

## Operator checklist (go-live smoke)

Do this on a real phone after Gateway + WhatsApp are already working.

1. [ ] Phone paired (`devices approve` + node connected).
2. [ ] **Status** shows Gateway online; kill switches idle (not frozen/paused).
3. [ ] WhatsApp DM: “Add a todo: buy oat milk” → todo appears on Android **Todos** with same title.
4. [ ] Complete the todo on Android → agent/store reflects done (WhatsApp confirm optional).
5. [ ] Trigger a **hard** action (e.g. propose buy/book/self-mod from WhatsApp) → Android **Inbox** shows pending card with Accept/Deny/Edit.
6. [ ] **Deny** → adapter execute count stays 0; card terminal.
7. [ ] Re-propose → **Accept** once → action executes once; second Accept/execute blocked.
8. [ ] Self-mod proposal → card shows **Code change** (or **policy-change**) + diff/files/rollback.
9. [ ] Status → **Freeze spending** (or freeze self-mod) → matching Accept path refuses execute.
10. [ ] Status → **Cancel pending** clears inbox; agent stays fail-closed.

If any step fails, fix pairing/TLS/config before enabling shopping, bookings, or self-mod in production.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Pairing required / stuck pending | `openclaw devices list` → approve exact `requestId`; retry Connect |
| Connected but no node commands | Node capability approval still pending (`nodes approve`) |
| Tailscale pair fails on `ws://` | Switch to Tailscale Serve / `wss://` |
| Todos missing after WhatsApp create | Android enabled in config; node connected; Gateway todos store path writable |
| Hard action never appears | Prefer Android for hard tier; confirm approval store path; check expiry |
| Accept does nothing | Already denied/expired/cancelled elsewhere; Status freezes; call-mode session |
| Limited access only | Use `wss://` setup code / `openclaw qr` for Full operator access |

## CI vs production

| Path | What runs |
| --- | --- |
| Production | Real OpenClaw Android node + this runbook + `android.example.yaml` |
| CI / harness | `AndroidProjectionApi` + `AndroidApprovalInboxApi` + Status double (`android.harness.json`); E2E-03 todos, TASK-11 / E2E-04..08 Accept/Deny |

Do not disable INV-* or swap production for stubs in CI. Keep `make test-ci` green with doubles.
