# Self-mod fixtures

Tiny sample workspace + path allowlist for diff → hard-approve → apply tests.

| Path | Role |
| --- | --- |
| `allowlist.json` | Allowed / policy / forbidden globs (`INV-SELF-001`) |
| `sample-workspace/` | Mini-repo mounted as allowlisted workspace copy |
| `patches/quiet-hours.json` | E2E-08 quiet-hours proposal metadata |

See [`agent-plan/capabilities/self-modification.md`](../../agent-plan/capabilities/self-modification.md)
and [`agent-plan/testing/components/self-modification.md`](../../agent-plan/testing/components/self-modification.md).
