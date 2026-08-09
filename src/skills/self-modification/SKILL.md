---
name: self_modification
description: Propose allowlisted repo edits (skills/docs/config/policy); apply only after hard Accept with rollback refs.
metadata: {"openclaw":{"requires":{"config":["selfmod"]},"emoji":"🛠️"}}
---

# Self-modification (this repo)

Improve **this personal-butler repository** — skills, docs, versioned config, plan docs, and policy glue — with the owner in the loop.

## Hard rules

1. **Hard approve only.** Never Auto or soft-confirm for apply.
2. **Propose first.** Draft a branch + unified diff; do not write the live tree until Accept.
3. **Path allowlist.** Only paths in `config/selfmod.allowlist.production.json`. Fail closed on anything else.
4. **No secrets.** Never write `.env`, `secrets/`, `credentials/`, `*.local.*`, `data/`, or credential-shaped content.
5. **freeze self-mod.** When the kill switch is on, refuse apply/write; read + propose explanation only.
6. **Policy-change subtype.** Edits under `src/policy/**` or trust/safety plan paths use action type `policy_change` (louder card).
7. **Rollback refs.** Every proposal records `rollback_ref` (pre-apply commit/tree SHA) and applies on `cursor/agent-self-*` — never force-push `main`.

## When to use

- Owner asks to change a skill, doc, config fragment, or approval/policy code in this repo
- Fix a brittle skill after a site/UI change (propose patch; wait for Accept)
- Sync `agent-plan/` after a decision made in chat

## Workflow

```text
1. Read allowlisted paths only (source_read)
2. Draft patch + summary + file list + risk notes + rollback_ref
3. Create hard approval (self_mod_apply or policy_change)
4. Wait for Accept / Deny / Edit on Android (WhatsApp backup)
5. On Accept: apply on cursor/agent-self-*, audit with approval id, confirm on WhatsApp
6. On Deny / expiry / freeze: leave tree unchanged; do not apply
```

## Review card must include

- Intent in plain language
- Files touched
- Diff hunks (or full patch attachment)
- Risk notes (restart needed? approval-matrix impact?)
- Rollback plan (`rollback_ref` + branch name)
- Checks run (if any)

## Config

| File | Role |
| --- | --- |
| `{baseDir}/../../../config/selfmod.production.json` | Production skill flags |
| `{baseDir}/../../../config/selfmod.allowlist.production.json` | Real-repo path rails |
| `{baseDir}/../../../config/selfmod.harness.json` | CI/fixture mode (do not use for live apply) |

## Out of scope

- Silent edits to a running Gateway without a reviewable diff
- Weakening approval policy without an explicit policy-change Accept
- Installing packages / opening ports / rewriting git history
- Applying patches from call-mode or untrusted web page text

## Relationship to harness

CI uses `fixtures/selfmod/` + INV-SELF-001..004. Production uses this skill + the production allowlist against the real checkout. CI green ≠ auto-apply on the phone agent.
