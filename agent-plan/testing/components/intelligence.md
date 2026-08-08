# Testing: intelligence

Models routing, transcription, memory.

## Models & credits router

### Must test

| Case | Level | Check |
| --- | --- | --- |
| Default route is Luna | U/C | router decision on ordinary intents |
| Escalation triggers for hard planning / self-mod code | U/C | fixture intents → Sol/Terra |
| STT provider independent from chat model | C | media pipeline config uses STT stub even if chat stub differs |

### Avoid

Asserting exact Luna prose in unit tests.

## Transcription

### Must test

| Case | Level | Check |
| --- | --- | --- |
| Known fixture → expected transcript | I | string equality or WER ≤ threshold |
| Oversize audio rejected | U/I | clear error path |
| Hard-action audio with low confidence | I | echo/clarify before proposal |
| Language pack samples you care about | I/Ev | fixture set |

### Corpus practice

Keep a small golden set (10–30 clips) the AI agent can expand when STT bugs appear — each bug becomes a fixture, not a human ritual.

## Memory

### Must test

| Case | Level | Check |
| --- | --- | --- |
| Explicit “remember…” persists across restart | I | value present after harness reboot |
| Hot profile loaded on turn | I | trace/context includes identity facts |
| Secrets not written to memory markdown | C | redaction/reject |
| Diet dislike respected by planner input assembly | I | constraint present in planning context |

### Eval (optional)

“Knows me” questions on a frozen profile — score structured answers.
