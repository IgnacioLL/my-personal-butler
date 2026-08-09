# Hosting

## Goal

Keep the OpenClaw Gateway reachable enough for WhatsApp webhooks/sessions, cron, calls, and Android pairing — without unnecessary cloud complexity.

## Options

| Option | Pros | Cons | Fit |
| --- | --- | --- | --- |
| Home machine always on | simple, private | power/network dependency | good if stable |
| Small VPS | always online, public webhook easier | monthly cost, more exposure surface | **recommended default** |
| Laptop only | cheap | sleeps = agent dies | poor for reminders/calls |

## Recommendation

Start on a **small always-on VPS** (or equivalent always-on mini PC) running OpenClaw Gateway:

- WhatsApp channel connected
- voice-call webhooks via stable HTTPS URL
- Android node paired ([pairing runbook](../../docs/android-pairing.md), [`config/android.example.yaml`](../../config/android.example.yaml))
- backups of config + memory

## Network / exposure

- Do not leave admin UI open to the world
- Use tunnel/reverse proxy with auth as needed
- Lock channel allowlists
- Separate browser profile for booking/shopping skills

## Backup & recovery

Backup at least:

- OpenClaw config
- memory/profile data
- task/approval DB
- skill configs (shops, caps)

Test restore once before relying on bookings/purchases.

## Acceptance criteria

- [ ] Gateway survives reboot (daemon/service)
- [ ] WhatsApp reconnect strategy documented
- [ ] Cron still fires after restart
- [ ] Backup/restore path exists
