# Models and credits

## Goal

Run the agent mainly on **GPT-5.6 Luna** through your **Codex / ChatGPT subscription**, while keeping quality high enough for life tasks and not burning premium quota on trivial turns.

## Model roles

| Role | Model | Used for |
| --- | --- | --- |
| Default brain | **Luna** | chat, reminders, light planning, most tool routing |
| Balanced | Terra (optional) | medium planning, multi-constraint days |
| Heavy | Sol (rare) | hard weekly plans, messy booking conflicts, deep research, non-trivial self-mod patches |
| STT | Dedicated transcription model | WhatsApp / call audio → text |
| TTS | Cheap/natural TTS | optional spoken WhatsApp replies |

Exact STT choice lives in [transcription.md](./transcription.md).

## Routing policy

Escalate above Luna when:

- multi-day plan with calendar + diet + travel constraints
- booking flow failed once and needs richer browser reasoning
- user explicitly asks for a deep plan
- non-trivial self-modification (multi-file code, policy changes)

Stay on Luna when:

- reminders, todos, FAQs from memory
- “what’s on my calendar”
- simple diet swaps
- approval summaries
- tiny doc/skill wording tweaks (still hard-approved to apply)

## Credit hygiene

- Prefer short tool loops over long monologues
- Summarize browser pages; don’t stuff raw HTML into context
- Keep hot memory small; retrieve cold facts on demand
- Use heartbeat prompts that are cheap and structured

## OpenClaw configuration intent

- Provider: OpenAI / Codex subscription auth
- Default agent model: Luna
- Optional per-skill model override for booking/shopping planner and self-mod coding
- Failover: if subscription exhausted, degrade gracefully (notify on Android/WhatsApp) rather than silently billing unexpected API usage — policy TBD during implementation

## Acceptance criteria

- [ ] Luna is the default reply model
- [ ] Codex subscription is the primary credit path
- [ ] Escalation path to a stronger model exists
- [ ] STT is configured independently from the chat model
