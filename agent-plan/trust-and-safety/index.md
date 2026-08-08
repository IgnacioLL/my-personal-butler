# Trust and safety

The agent is only useful if it stays controllable.

## Documents

- [Approval matrix](./approval-matrix.md) — what runs auto vs needs Accept

## Non-negotiables

1. Allowlisted WhatsApp / caller identity only
2. Money and external reservations require hard approve
3. Call mode cannot purchase/book
4. Pending approvals expire
5. Global kill switches exist: pause agent, freeze spending, cancel all pending
6. Side effects are logged

## Threats we care about

| Threat | Mitigation |
| --- | --- |
| Prompt injection from web pages while booking | treat page content as untrusted; confirm final action |
| Wrong STT → wrong purchase | echo + hard approve |
| Agent loops / spam | rate limits, quiet hours |
| Stolen phone WhatsApp session | approvals still need device confirm for hard actions (defense in depth) |
| Over-permissioned browser session | isolate profiles; least privilege |

## Security setup checklist (implementation later)

- [ ] WhatsApp `allowFrom` locked
- [ ] Gateway not publicly exposed without auth/tunnel hardening
- [ ] Secrets outside memory markdown
- [ ] Approval expiry + audit log
- [ ] Spend caps configured before shopping skill enabled
