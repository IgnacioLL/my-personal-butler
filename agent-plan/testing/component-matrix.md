# Component test matrix

Tailored depth per area. **C** = contract/policy, **U** = unit, **I** = integration, **E** = e2e harness, **L** = live-smoke (optional), **Ev** = eval.

| Component | U | C | I | E | L | Ev | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WhatsApp allowlist / routing | | ● | ● | ● | ○ | | Safety-critical ingress |
| Voice note → STT → turn | | ● | ● | ● | ○ | ○ | Fixture audio corpus |
| TTS reply mode | | ○ | ● | ○ | | | Assert mode rules, not voice beauty |
| Outbound calls | ● | ● | ● | ○ | ○ | | Mock provider first |
| Android todos sync | | ● | ● | ● | ○ | | State equality assertions |
| Android approvals UI | | ● | ● | ● | ○ | | Snapshot/API; Accept/Deny drives state |
| Models router (Luna/Sol) | ● | ● | ○ | | | | Deterministic router tests w/ stubs |
| Transcription pipeline | ● | ● | ● | ● | ○ | ○ | WER thresholds on fixtures |
| Memory read/write | ● | ● | ● | ● | | ○ | No secrets in memory files |
| Reminders / cron | ● | ● | ● | ● | | | Fake clock mandatory |
| Habits escalation | ● | ● | ● | ● | | | WhatsApp → Android → call ladder |
| Todos | ● | ● | ● | ● | | | Dedup behavior |
| Calendar read/write | | ● | ● | ● | ○ | | Soft-confirm before write |
| Diet planning | | ○ | ● | ● | | ● | Structure + constraints; prose via eval |
| Bookings | | ● | ● | ● | ○ | | Simulate portal; never prod book in CI |
| Shopping | ● | ● | ● | ● | ○ | | Caps + freeze + no execute pre-approve |
| Self-modification | ● | ● | ● | ● | | | Diff-only until Accept; path allowlist |
| Approval matrix engine | ● | ● | ● | ● | | | Property tests across action types |
| Kill switches | ● | ● | ● | ● | | | pause / freeze spend / freeze self-mod |
| Hosting reboot resilience | | ○ | ● | ○ | ○ | | Restart preserves pending approvals |

● = required before calling the capability “done”  
○ = optional / later / flagged

## How to use this matrix

1. When implementing a capability, open its row and add the required test kinds first.
2. Do not expand live-smoke until harness e2e is green.
3. If a cell is empty, that kind of test is low value for that component — skip on purpose.

## Per-area deep dives

- [Channels](./components/channels.md)
- [Intelligence](./components/intelligence.md)
- [Capabilities](./components/capabilities.md)
- [Trust and approvals](./components/trust-and-approvals.md)
- [Self-modification](./components/self-modification.md)
