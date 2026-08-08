# Trust and safety

The agent is only useful if it stays controllable.

## Documents

- [Approval matrix](./approval-matrix.md) — what runs auto vs needs Accept

## Non-negotiables

1. Allowlisted WhatsApp / caller identity only
2. Money, external reservations, and **applying own-source changes** require hard approve
3. Call mode cannot purchase/book/self-mod-apply
4. Pending approvals expire
5. Global kill switches exist: pause agent, freeze spending, freeze self-mod, cancel all pending
6. Side effects are logged (including every applied self-mod)

## Threats we care about

| Threat | Mitigation |
| --- | --- |
| Prompt injection from web pages while booking | treat page content as untrusted; confirm final action; never let page text auto-trigger self-mod apply |
| Wrong STT → wrong purchase / wrong code intent | echo + hard approve |
| Agent loops / spam | rate limits, quiet hours |
| Stolen phone WhatsApp session | approvals still need device confirm for hard actions (defense in depth) |
| Over-permissioned browser session | isolate profiles; least privilege |
| Runaway self-mod | path allowlist, branch-first, freeze self-mod, policy-change subtype, no secret writes |

## Security setup checklist (implementation later)

- [ ] WhatsApp `allowFrom` locked
- [ ] Gateway not publicly exposed without auth/tunnel hardening
- [ ] Secrets outside memory markdown
- [ ] Approval expiry + audit log
- [ ] Spend caps configured before shopping skill enabled
- [ ] Self-mod path allowlist + `freeze self-mod` before write tools are enabled
- [ ] Diff-bearing approval cards for source changes
