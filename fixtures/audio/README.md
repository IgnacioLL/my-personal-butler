# Audio fixtures

Short voice-note placeholders and expected transcripts for STT harness tests
(`audio id/path → transcript` map). No real PII / no live recordings.

## Layout

| File | Purpose |
| --- | --- |
| `manifest.json` | Clip registry: id, path, outcome, expected transcript, clarification |
| `*.ogg` | Tiny deterministic placeholder bytes (not real Opus/OGG audio) |

## Clip outcomes

| Outcome | Behavior |
| --- | --- |
| `ok` | Transcript turn: `[Audio] <text>` |
| `empty` / `garbage` / `unknown` | Clarification ask; no hard actions |
| `low_confidence` | Echo transcript + clarify (esp. hard-action language) |
| `oversize` | Rejected by max_bytes / duration bound → clarification |

## E2E-01 dependency

`fx-reminder` → `Remind me Sunday at 18:00 to call grandma.`

See [`agent-plan/testing/harnesses-and-fixtures.md`](../../agent-plan/testing/harnesses-and-fixtures.md)
and [`agent-plan/intelligence/transcription.md`](../../agent-plan/intelligence/transcription.md).
