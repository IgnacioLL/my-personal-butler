# Harnesses and fixtures

## Purpose

Give an AI agent (and CI) a way to **drive the system like a user** without WhatsApp in the loop, while still testing the same state transitions.

## Core harness idea: Virtual User

A scripted client that can:

- inject text turns as if from allowlisted WhatsApp
- inject audio fixtures into the media/STT pipeline
- advance a fake clock
- Accept / Deny / Edit approvals via the same API the Android node uses
- read resulting state: todos, reminders, calendar fake, audit log, outbound message inbox

```text
Virtual User  →  Gateway (test profile)  →  mocked tools/adapters
      ↑                                         │
      └──────── assert state + artifacts ←──────┘
```

## Required mocks / doubles

| Dependency | Double | Assert against |
| --- | --- | --- |
| WhatsApp transport | inbound injector + outbound catcher | messages sent, allowlist rejects |
| STT | fixture map `audio → transcript` (+ error cases) | transcript attached to turn |
| TTS | noop/spy | called only when policy says |
| Voice call provider | `mock` provider | call placed, tool allowlist |
| Calendar | in-memory calendar | events proposed/created |
| Browser/Booksy | stub portal or recorded session | slot proposals; book execute count |
| Commerce | dry-run merchant | charge attempts |
| Android node | API-level approval/todo client | projection sync |
| LLM | stub tool-calling model **or** recorded traces | for policy tests prefer stubs; for eval use frozen traces |

## Fixture packs

Store under something like `fixtures/` (implementation later):

- `audio/` — short voice notes + expected transcripts (multi-language if needed)
- `approvals/` — sample payloads for buy/book/self-mod
- `calendar/` — busy weeks, conflicts, timezones
- `memory/` — seed profiles (diet prefs, grandma ritual)
- `browser/` — Booksy-like HTML/CRM stubs
- `selfmod/` — tiny sample repos / path allowlists for patch tests

Fixtures must be deterministic and free of real secrets/PII.

## Artifacts every run should write

| Artifact | Why |
| --- | --- |
| `report.json` | machine pass/fail for agent loops |
| `report.md` | quick human/AI reading |
| `trace.jsonl` | tool calls + approvals |
| `outbound-messages.json` | what would have gone to WhatsApp |
| `ui/` snapshots (if any) | Android approval cards |
| `diffs/` | self-mod proposals |

## Fake clock

API intent:

- `clock.now()`
- `clock.advance(duration)`
- cron/heartbeat reads the fake clock in harness env only

## Deterministic LLM strategy

For **safety and routing tests**, do not call Luna live:

- inject a stub model that returns planned tool calls for the scenario
- or replay a recorded successful trace

For **quality evals**, call the real model in a separate lane with scoring rubrics and budgets.

This split keeps CI autonomous and cheap while still allowing model-quality measurement.
