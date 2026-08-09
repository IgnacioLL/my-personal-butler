# Testing: self-modification

Dangerous capability → testing is mostly about **proving it cannot run away**.

## Unit

- path allowlist glob matching
- secret-pattern scanner on diffs
- diff size ceiling policy

## Contract

- propose tools available; apply tools gated
- `freeze self-mod` removes apply/write
- policy-change subtype required when touching approval/kill-switch files (path heuristics)

## Integration / e2e

Use a **fixture mini-repo** (not the full production tree) mounted as allowlisted workspace:

1. Agent proposes quiet-hours patch
2. Working tree unchanged pre-Accept
3. Accept applies on a branch; commit SHA recorded
4. Deny leaves tree clean
5. Outside-allowlist path attempt fails closed
6. Optional reload approval is separate

## Checks that make AI autonomy easy

Prefer filesystem & git assertions:

- `git status` / `git diff` empty before Accept
- after Accept: expected file hunk present
- `rollback_ref` points to parent commit

Do not require a human to read the diff for CI green — but store the diff artifact for audit.

## Non-goals for CI

- Agent freely rewriting the real `main` branch of the personal butler repo
- Network install of new global packages as part of a test

Production rails (PROD-09) are validated by **path-matching smoke only** against
`config/selfmod.allowlist.production.json` + skill presence — never by applying
patches to the live checkout in `test:ci`.

## Product doc

[`../../capabilities/self-modification.md`](../../capabilities/self-modification.md)
