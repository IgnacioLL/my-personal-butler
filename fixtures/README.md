# Fixtures

Deterministic inputs for harnesses and CI. **No real secrets or PII.**

Per [`agent-plan/testing/harnesses-and-fixtures.md`](../agent-plan/testing/harnesses-and-fixtures.md):

| Pack | Directory | Use |
| --- | --- | --- |
| Voice / STT | [`audio/`](./audio/) | Short voice notes → expected transcripts |
| Approvals | [`approvals/`](./approvals/) | Sample buy / book / self-mod payloads |
| Calendar | [`calendar/`](./calendar/) | Busy weeks, conflicts, timezones |
| Memory | [`memory/`](./memory/) | Seed profiles (diet prefs, rituals) |
| Browser | [`browser/`](./browser/) | Booksy-like HTML / portal stubs |
| Shopping | [`shopping/`](./shopping/) | Dry-run merchant catalog (protein powder, caps) |
| Self-mod | [`selfmod/`](./selfmod/) | Tiny sample workspaces + path allowlists |

TASK-01+ will populate packs as tests land.
