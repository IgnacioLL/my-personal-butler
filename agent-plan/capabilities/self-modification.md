# Self-modification (edit own source)

## Purpose

Let the agent improve itself — skills, config, docs, and custom code in **this repository** — with you in the loop.

This is powerful and dangerous. It is always **hard-approved**. The agent may propose and prepare changes; it may not apply them until you Accept.

## Why include it

- Fix brittle Booksy/browser skills when sites change
- Add a new reminder policy or approval rule without you hand-editing everything
- Keep `agent-plan/` docs in sync after decisions made in chat
- Grow the system continuously with human oversight

## Scope

### In scope (with hard approve)

- Skills / prompts / procedural markdown in this repo (`src/skills/**`)
- Agent config fragments that are versioned here (`config/**`, excluding local/secret files)
- Plan docs under `agent-plan/` and operator docs under `docs/`
- Custom glue code owned by this project (especially `src/policy/**` → policy-change)
- Tests / scripts that validate a change (`tests/**`, `scripts/**`)

### Out of scope / Forbidden without a separate design

- Silent edits to the live running Gateway without a reviewable diff
- Changing approval policy to weaken itself (e.g. auto-buy) without explicit hard approve of that policy diff
- Rotating secrets / writing credentials into the repo
- Destructive git history rewrites (`force-push`, `reset --hard` on main)
- Installing new system packages or opening network expose ports without a dedicated approval type
- Editing files outside the allowlisted project paths

## Production allowlist (this repo)

Canonical rails: [`config/selfmod.allowlist.production.json`](../../config/selfmod.allowlist.production.json)

| Allowed (examples) | Forbidden (examples) |
| --- | --- |
| `src/skills/**`, `docs/**`, `config/**`, `agent-plan/**`, `scripts/**`, `tests/**`, `src/policy/**`, `data/memory/**` | `.env*`, `secrets/**`, `credentials/**`, `config/*.local.*`, `data/secrets/**`, `data/approvals/**`, `data/todos/**`, `.git/**` |

Personal memory (`data/memory/profile.json`, `episodes.jsonl`) is versioned like skills: durable updates commit into this repository (Soft tier via `memory_update`, not silent host-only files).

Production skill/config:

- Skill: [`src/skills/self-modification/SKILL.md`](../../src/skills/self-modification/SKILL.md)
- Config: [`config/selfmod.production.json`](../../config/selfmod.production.json)
- CI fixture (INV-SELF): [`fixtures/selfmod/`](../../fixtures/selfmod/) + [`config/selfmod.harness.json`](../../config/selfmod.harness.json)

Loader: `capabilities.selfmod.production` (`load_production_config`, `production_paths_smoke`).

## Hard-coded rule

**No source write lands without your Accept.**

Even if you say “just fix it” in WhatsApp, the runtime must still create a hard-approval item that shows the diff (or patch summary). Soft confirm is not enough. Auto is forbidden.

## Preferred workflow

```text
You: “Add quiet hours so it never calls after 22:00”
  → Agent explores allowlisted repo paths (read-only)
  → Drafts a branch + patch (or unified diff)
  → Runs cheap checks if available (lint/tests)
  → Opens hard approval: summary + file list + diff preview
  → You Accept / Deny / Edit on Android (WhatsApp backup)
  → On Accept: apply patch, commit on a branch, report result
  → Optional: restart/reload only the affected skill — never blind full prod rewrite
```

### Collaboration modes

| Mode | What the agent does | When |
| --- | --- | --- |
| **Propose only** | Diff + explanation, you apply manually | Default early on |
| **Apply on Accept** | Writes files after hard approve | Once trusted |
| **Pair fix** | You describe failure; agent iterates on a branch with repeated Approves | Skill breakages |

## Review card contents

Every self-mod approval must show:

- intent in plain language
- files touched
- diff hunks (or link/attachment to full patch)
- risk notes (restarts needed? approval-matrix impact? outbound side effects?)
- rollback plan (previous commit SHA / branch name)
- checks run (and results)

## Safety rails

1. **Path allowlist** — only configured project directories (production file above; fixtures for CI)
2. **Branch-first** — prefer `cursor/agent-self-…` branches; protect `main`
3. **Diff ceiling** — huge patches require split Approves or Sol-tier review summary
4. **Policy self-guard** — changes to approval/kill-switch code are a special approval subtype (“policy change”) and should be visually louder
5. **No credential writes** — secrets stay in env/secret store
6. **Reload boundary** — applying code ≠ auto-restarting Gateway unless you approve restart too
7. **Audit log** — every applied self-mod is logged with approval id
8. **Kill switch** — `freeze self-mod` disables write tools entirely (read still ok)

## Model guidance

- Luna can triage and draft small doc/skill edits
- Escalate to Terra/Sol for non-trivial code changes
- Never let call-mode or web-page content directly trigger apply; untrusted text can only create a proposal

## Failure handling

| Case | Behavior |
| --- | --- |
| Patch does not apply cleanly | stop; show conflict; do not force |
| Checks fail after apply | offer revert approval (or auto-revert if pre-agreed safe) |
| Agent tries to edit outside allowlist | hard fail + notify |
| Approval expires | discard unapplied branch/patch; notify once |

## Relationship to OpenClaw

Use Gateway tools for workspace read/write **behind** the approval gate. Do not give the daily chat session unconstrained shell/`write` on the agent repo. Self-mod should be a dedicated skill with its own tool policy.

Load the production skill from `src/skills/self-modification/` into the Gateway workspace (`skills/` or `skills.load.extraDirs`). CI must continue to use the fixture mini-repo — never apply self-mod to the live checkout inside `test:ci`.

## Acceptance criteria

- [x] Agent can read its allowlisted source and propose a diff
- [x] Apply path is unreachable without hard Accept
- [x] Approval card shows files + diff + rollback
- [x] `freeze self-mod` blocks writes immediately
- [x] Policy-matrix edits are labeled as higher-risk approvals
- [x] Successful apply is audited and reported on WhatsApp
- [x] Production allowlist covers real repo skills/docs/config (not secrets); INV-SELF stays green on fixtures
