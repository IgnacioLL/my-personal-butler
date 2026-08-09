# Personal Agent — Implementation Status

Planner-owned tracker. Source of truth for delegated work against `agent-plan/` (product + testing).

**Planner role:** delegate only — no exploration, no coding.  
**Sub-agents:** explore → plan → implement → test → review → update this file.

**Model policy:** hard / safety-critical → `cursor-grok-4.5-high`; scaffolding / medium → `composer-2.5` (non-fast).  
**Pairing:** 2 agents per task (A = implement, B = review/verify) unless noted.

**Primary docs:** `agent-plan/index.md`, `agent-plan/operations/roadmap.md`, `agent-plan/testing/roadmap.md`, `agent-plan/testing/autonomous-agent-process.md`.

---

## Legend

| Status | Meaning |
| --- | --- |
| `pending` | Not started |
| `queued` | Assigned / about to run |
| `in_progress` | Agent(s) working |
| `review` | Implement done; reviewer running |
| `blocked` | Needs fixture, dep, or decision |
| `done` | Code + tests + status update complete |
| `failed` | Attempted; needs re-dispatch |

---

## Global gates

| Gate | Status | Notes |
| --- | --- | --- |
| `test:ci` exists and fails closed on broken invariant | done | `make test-ci` PASS; `make test-ci-fail-closed` proves broken INV rejected |
| Artifacts under `artifacts/test/` | done | `artifacts/test/ci/{report.json,report.md,verification.json}` |
| Fake clock utility | done | `src/harness/clock.py` — `now()` / `advance(duration)` |
| INV-* runner skeleton | done | `src/harness/inv_runner.py` + `src/invariants/` |
| Virtual User harness | done | `src/harness/virtual_user.py` — inject audio/text, create reminders, assert state (E2E-01 gate) |
| Phase exits require matching T* unlock | done | **T8 exit PASS** (TASK-25); **CI gate map PASS** (TASK-26): `docs/ci-gates.md` ↔ `agent-plan/testing/ci-gates.md`; `gate_e2e` E2E-01..10 + `gate_deny_paths` E2E-04/06/07/08 |

---

## Task board

### TASK-00 — Workspace bootstrap & repo layout
- **Phase:** 0 / T0
- **Depends on:** —
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Create implementable repo skeleton around the plan (not only docs): package/workspace layout suitable for OpenClaw Gateway skills/tools, `README` pointing at `agent-plan/`, dirs for `src/` (or agreed layout), `fixtures/`, `artifacts/test/`, `scripts/`, config placeholders. Do **not** invent a custom runtime — prefer OpenClaw primitives per architecture.
- **Acceptance:** Layout committed; empty `test:ci` stub or documented command; B reviews against architecture.md.
- **Result:** PASS (Agent B review) — Layout matches OpenClaw Gateway–centric architecture (`src/skills`, `src/tools`, `config/` placeholders); six fixture packs + `artifacts/test/` convention present; `agent-plan/` untouched. `./scripts/test-ci.sh`, `make test-ci`, and `make test` exit 0 (T0 stub). Review fix: README `make test:ci` → `make test-ci` to match Makefile. Ready for TASK-01 (INV runner, fake clock).
- **Artifacts:** `README.md`, `Makefile`, `.gitignore`, `config/`, `src/`, `fixtures/{audio,approvals,calendar,memory,browser,selfmod}/`, `artifacts/test/`, `scripts/test-ci.sh`

### TASK-01 — Test harness scaffolding (T0)
- **Phase:** 0 / T0
- **Depends on:** TASK-00
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Per `testing/roadmap.md` T0 + `harnesses-and-fixtures.md`: `test:ci` pipeline (unit/contract/integration stubs), artifact directory convention, fake clock, INV-* runner skeleton that **fails** on a deliberate broken invariant, outbound message catcher stub.
- **Acceptance:** `test:ci` runs; deliberate broken INV fails CI; B verifies autonomy process checklist items for scaffolding.
- **Result:** PASS (Agent B review) — T0 checklist verified by re-run: repo test scaffolding ✓ (`make test-ci` exit 0); artifacts under `artifacts/test/ci/` ✓ (`report.json`/`verification.json`/layer reports + outbound-messages); fake clock ✓; INV runner fails on deliberate broken INV ✓ (`--break-invariant` exit 1; `make test-ci-fail-closed` exit 0); WhatsApp allowlist contract stubs ✓ (`INV-INGRESS-001/002`); outbound catcher stub ✓. Review fix: `scripts/test-ci.sh` capture status under `set -e` so FAIL path still prints artifact hints. Ready for TASK-02/03.
- **Artifacts:** `src/harness/{clock,outbound,ingress_sim,inv_runner,artifacts}.py`, `src/policy/ingress.py`, `src/invariants/inv_ingress_00{1,2}.py`, `src/invariants/inv_t0_clock.py`, `scripts/run_test_ci.py`, `scripts/test-ci.sh`, `Makefile` (`test-ci`, `test-ci-fail-closed`), `artifacts/test/ci/` (runtime; gitignored)

### TASK-02 — Trust core: approval matrix engine + kill switches
- **Phase:** 0 (foundation for all gated work)
- **Depends on:** TASK-00, TASK-01
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Implement approval item schema + status machine (`pending|accepted|denied|expired|executed|failed|cancelled`), tiers from `trust-and-safety/approval-matrix.md`, kill switches (`pause agent`, `freeze spending`, `freeze self-mod`, `cancel pending`). Contract tests for `INV-APPR-001..004`, `INV-KILL-001..002`, `INV-AUDIT-001` (as applicable at this stage).
- **Acceptance:** Invariants green in harness; no hard action path without accept.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0 and `make test-ci-fail-closed` exit 0. Contract checks green: `INV-APPR-001..004`, `INV-KILL-001..002`, `INV-AUDIT-001`. Spot-check: denied/expired cannot execute; clock TTL → expired without adapter call; cancel pending → cancelled + blocked; pause stops cron; successful gated write audits with approval id; freeze spending/self-mod block execute. No code fixes required. Ready for TASK-03+.
- **Artifacts:** `src/policy/{approvals,kill_switches,audit,action_gateway}.py`, `src/harness/adapters.py`, `src/invariants/inv_{appr_00{1,2,3,4},kill_00{1,2},audit_001}.py`, `fixtures/approvals/sample-items.json`, `artifacts/test/{ci,task-02}/` (runtime; gitignored)

### TASK-03 — WhatsApp ingress allowlist + routing (INV-INGRESS-*)
- **Phase:** 0 / T0
- **Depends on:** TASK-01
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Allowlisted DM only; groups off; non-allowlisted → no tools / no side effects. Contract tests `INV-INGRESS-001`, `INV-INGRESS-002`. Mock WhatsApp transport per harnesses doc.
- **Acceptance:** T0 WhatsApp allowlist contract tests green; B adversarial cases.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0 and `make test-ci-fail-closed` exit 0. Adversarial spot-checks: stranger/spoof/empty allowlist/flood → zero tools+outbound; group_id without flag, `@g.us`, broadcast, group-JID-on-allowlist → `groups_disabled`; mixed DM→group stable. Review fix: classify `@newsletter` as non-DM (Channels) so mis-allowlisted channel JIDs cannot run agent; INV-INGRESS-002 coverage extended. `INV-INGRESS-003` scaffold intact for TASK-06. Ready for TASK-06 transcription.
- **Artifacts:** `src/harness/whatsapp_transport.py`, `src/harness/ingress_sim.py`, `src/policy/ingress.py`, `src/invariants/inv_ingress_00{1,2,3}.py`, `scripts/run_test_ci.py`, `artifacts/test/{ci,task-03}/` (runtime; gitignored)

### TASK-04 — Personal memory profile + read/write
- **Phase:** 0→1 / T1
- **Depends on:** TASK-00
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Seed memory profile template; hot profile + episodic write/read per `intelligence/memory.md`. Integration tests; no secrets in memory files.
- **Acceptance:** Memory R/W integration green; fixture seed profile exists.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0 and `make test-ci-fail-closed` exit 0. Spot-checks: fixture `seed-profile.json` seeds hot profile (Alex, grandma household, peanuts allergy); explicit `remember` + episodic append survive `MemoryStore.open` reboot; `INV-MEM-001` + integration reject `token:`/`sk-`/AWS/GitHub patterns with no disk leak. `INV-MEM-*` intact; no gaps requiring code fix. Ready for TASK-07 (reminders can use `hot_context_lines` / `planning_constraints`).
- **Artifacts:** `src/intelligence/memory/{store,secrets}.py`, `src/invariants/inv_mem_001.py`, `fixtures/memory/seed-profile.json`, `scripts/run_test_ci.py`, `artifacts/test/{ci,task-04}/` (runtime; gitignored)

### TASK-05 — Hosting / Gateway config skeleton + reboot durability hooks
- **Phase:** 0
- **Depends on:** TASK-00
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Documented/config scaffolding for always-on Gateway per `operations/hosting.md`; backup paths; restart preserves pending approvals (prep for E2E-10). No live VPS required — harness-friendly config.
- **Acceptance:** Config templates + tests that approval store survives harness restart.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0 and `make test-ci-fail-closed` exit 0. Spot-checks: pending buy approval survives `ActionGateway` reopen + `ApprovalStore.open()` + `GatewayHarness.restart()`; Accept executes once after restart (`buy_count=1`, second execute blocked, status=executed). Config templates (`gateway.harness.json`, `backup.example.json`, hosting section) load; `INV-APPR/KILL/AUDIT/INGRESS/MEM-*` intact. No code fixes required. Ready for TASK-06 / E2E-10 prep.
- **Artifacts:** `src/policy/approvals.py`, `src/policy/action_gateway.py`, `src/harness/{gateway_profile,gateway_harness}.py`, `config/{gateway.harness.json,backup.example.json,gateway.example.yaml,README.md}`, `scripts/backup-restore-placeholder.sh`, `scripts/run_test_ci.py`, `artifacts/test/task-05/` (runtime; gitignored)

### TASK-06 — Transcription pipeline (WhatsApp audio → turn)
- **Phase:** 1 / T1
- **Depends on:** TASK-03, TASK-01
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** STT stub + audio fixture pack; every voice note → transcript or clarification (`INV-INGRESS-003`); optional TTS policy hooks. See `intelligence/transcription.md`.
- **Acceptance:** Fixture map audio→transcript; E2E-01 dependency ready.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0 and `make test-ci-fail-closed` exit 0. Spot-checks: `fx-reminder` → `[Audio] Remind me Sunday at 18:00 to call grandma.`; empty/garbage/oversize/unknown/low-conf buy → clarification; no hard tools on unclear audio (`INV-INGRESS-003`). Review fix: enforce manifest `max_duration_sec` (duration-only oversize) — was declared but unused. E2E-01 STT dependency ready. Ready for TASK-07.
- **Artifacts:** `src/intelligence/transcription/{stt,tts,pipeline}.py`, `fixtures/audio/{manifest.json,*.ogg}`, `src/harness/whatsapp_transport.py`, `src/invariants/inv_ingress_003.py`, `scripts/run_test_ci.py`, `artifacts/test/task-06/`

### TASK-07 — Reminders + habits (fake clock)
- **Phase:** 1 / T1
- **Depends on:** TASK-01, TASK-04, TASK-06
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** One-shot + recurring reminders; habit schedules; cron via fake clock. Per `capabilities/reminders-and-habits.md`. Auto approval tier.
- **Acceptance:** Unit + integration with clock.advance; outbound confirm captured.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0 and `make test-ci-fail-closed` exit 0. Spot-checks: parse “Remind me Sunday at 18:00 to call grandma” → Sunday 18:00 / body call grandma; `FakeClock.advance` fires outbound `Reminder: call grandma`; `reminder_create`/`habit_create` Auto with zero hard approval items. Review fix: fail-closed must not stomp `artifacts/test/task-07/` verification. INV-* intact. E2E-01 create/fire ready.
- **Artifacts:** `src/capabilities/reminders/{parse,store,scheduler,service}.py`, `src/policy/action_gateway.py`, `scripts/run_test_ci.py`, `artifacts/test/task-07/`

### TASK-08 — E2E-01 Voice reminder journey
- **Phase:** 1 / T1
- **Depends on:** TASK-06, TASK-07, Virtual User (TASK-01)
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Full E2E-01 from `testing/e2e-flows.md` with stubs; write `artifacts/test/e2e-01/` + verification.json.
- **Acceptance:** T1 exit — voice-note reminder green without human phone.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-01` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0. Spot-checks: due=2026-01-11T18:00:00+01:00 (Mon 2026-01-05 → next Sunday 18:00 Europe/Madrid); hard=0 / pending=0 / approval_id=None / tier=auto. Fail-closed does not stomp e2e-01 verification (still PASS). INV-* intact. No code gaps. **T1 exit met** — voice-note reminder green without a human phone.
- **Artifacts:** `src/harness/virtual_user.py`, `scripts/run_e2e_01.py`, `scripts/run_test_ci.py` (e2e layer), `Makefile` (`e2e-01`), `artifacts/test/e2e-01/{report.json,verification.json,outbound-messages.json,reminders.json,trace.jsonl}`

### TASK-09 — Models router (Luna default / Terra-Sol escalate) stubs
- **Phase:** 1
- **Depends on:** TASK-00
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Deterministic router tests w/ stubs per `intelligence/models-and-credits.md`. No live Luna in CI gates.
- **Acceptance:** Router unit/contract green.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01` exit 0. Spot-checks: Luna for reminder/todo/general hello (`luna_intent` / `default_luna`, no escalation); Sol for deep-plan phrase (`deep_plan_request`), multi-day calendar+diet+travel, policy change, multi-file self-mod; Sol wins over Terra when both signals present. Fixture table 15/15 via `RoutingSignals.from_dict`. `INV-MODEL-001/002` green; STT stub independent from chat model. Fail-closed does not stomp task-09 verification (still PASS). No code fixes required. Ready for TASK-10.
- **Artifacts:** `src/intelligence/models/{roles,router,stubs,fixtures}.py`, `src/invariants/inv_model_00{1,2}.py`, `fixtures/models/routing-intents.json`, `scripts/run_test_ci.py`, `artifacts/test/task-09/` (runtime; gitignored)

### TASK-10 — Todos + Android projection API
- **Phase:** 2 / T2
- **Depends on:** TASK-02, TASK-04
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Todo store + Android projection doubles; WhatsApp “add todo” → Android API equality. Per `capabilities/todos.md`, `channels/android-companion.md`.
- **Acceptance:** E2E-03 ready; state equality tests.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01` exit 0. Spot-checks: WhatsApp “Add todo: buy oat milk” Auto → Android `list_todos`/`get_todo` same id/title/open; `complete_todo` → store `done`; re-add “Buy oat milk” dedups (same id, `todo_dedup` outbound, one open row). E2E-03 Virtual User journey PASS (`gate: false`, prep for TASK-12). Review fix: remove duplicate `run_e2e_03` in `virtual_user.py`. Fail-closed does not stomp task-10/e2e-03 verification. INV-* intact. Ready for TASK-11.
- **Artifacts:** `src/capabilities/todos/{store,parse,service}.py`, `src/channels/android/projection.py`, `src/policy/{action_gateway,approvals}.py`, `src/harness/virtual_user.py`, `scripts/run_test_ci.py`, `artifacts/test/task-10/` (runtime; gitignored), `artifacts/test/e2e-03/` (runtime; gitignored)

### TASK-11 — Android approval inbox Virtual User wiring
- **Phase:** 2 / T2
- **Depends on:** TASK-02, TASK-10
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Accept/Deny/Edit via same API Android uses; Virtual User can exercise alone (T2 exit). Soft-confirm calendar path hooks for E2E-04.
- **Acceptance:** T2 exit criteria met.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01` exit 0. Spot-checks: soft propose → Android `list_pending` + `create_count=0`; Edit patches payload without create; Accept → `create_count=1` / executed; Deny → create unchanged + late execute fail-closed; hard buy Deny → `buy_count=0`. `android.approvals` is same `AndroidApprovalInboxApi` surface. Fail-closed does not stomp task-11 verification. INV-APPR-* intact (no weaken). **T2 exit PASS** — Accept/Deny by Virtual User alone. No code fixes required. Ready for TASK-12.
- **Artifacts:** `src/channels/android/approvals.py`, `src/channels/android/projection.py`, `src/policy/{approvals,action_gateway}.py`, `src/harness/virtual_user.py` (`run_t2_approval_inbox`), `scripts/run_test_ci.py`, `artifacts/test/task-11/` (runtime; gitignored)

### TASK-12 — E2E-03 Todo WhatsApp → Android
- **Phase:** 2 / T2
- **Depends on:** TASK-10, TASK-11
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Implement and green E2E-03; artifacts + verification stamp.
- **Acceptance:** Gate-tagged e2e green.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-03` exit 0, `make e2e-01` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0. Spot-checks: WhatsApp “Add todo: buy oat milk” Auto → Android `list_todos`/`get_todo` same id/title/open; `complete_todo` → store `done`. E2E-03 artifacts `gate: true` in `report.json` + `verification.json` (all five checks stamped). Fail-closed does not stomp e2e-03 verification. INV-* intact (no weaken). **T2 exit PASS** — E2E-03 todo sync gate green; Accept/Deny alone (TASK-11) already met. No code fixes required. Ready for Phase 3 (TASK-13+).
- **Artifacts:** `scripts/run_e2e_03.py`, `Makefile` (`e2e-03`), `scripts/run_test_ci.py` (e2e layer gate), `src/harness/virtual_user.py` (`run_e2e_03` gate stamp), `scripts/test-ci.sh`, `artifacts/test/e2e-03/{report.json,verification.json,todos.json,android-projection.json}` (runtime; gitignored)

### TASK-13 — Calendar read/write + soft confirm
- **Phase:** 3 / T3
- **Depends on:** TASK-11
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** In-memory calendar; conflict-aware suggestions; soft confirm before write (`INV-APPR-003`). Per `capabilities/calendar.md`.
- **Acceptance:** Integration + E2E-04 green.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01` exit 0, `make e2e-03` exit 0. Spot-checks: NL propose → `create_count=0` until Accept → `create_count=1`; Deny → create stays 0 / late execute fail-closed; busy-Friday conflict with Standup + free-slot suggestions, no write. Fail-closed does not stomp task-13 verification (`e2e04_ready=true`). `INV-APPR-003` intact (no weaken). No code fixes required. **E2E-04 ready** for TASK-14.
- **Artifacts:** `src/capabilities/calendar/{store,parse,service}.py`, `src/harness/{adapters,virtual_user}.py`, `fixtures/calendar/busy-friday.json`, `scripts/run_test_ci.py`, `artifacts/test/task-13/`

### TASK-14 — E2E-04 Calendar soft confirm
- **Phase:** 3 / T3
- **Depends on:** TASK-13
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Accept and deny paths; create count assertions.
- **Acceptance:** report.json PASS.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-04` exit 0, `make e2e-01` exit 0, `make e2e-03` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0. Spot-checks: `gate: true` on report + verification; `calendar_create_after_accept=1`, `calendar_create_after_deny=0`; pending soft confirm `create=0` until Accept; Deny + late execute blocked. `INV-APPR-003` intact (no weaken). No code fixes required.
- **Artifacts:** `src/harness/virtual_user.py` (`run_e2e_04`, `E2E04Result`), `scripts/run_e2e_04.py`, `Makefile` (`e2e-04`), `scripts/run_test_ci.py` (e2e layer), `scripts/test-ci.sh`, `scripts/README.md`, `artifacts/test/e2e-04/` (runtime; gitignored)

### TASK-15 — Diet & planning v1
- **Phase:** 3 / T3
- **Depends on:** TASK-04, TASK-13, TASK-10
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Diet plan from memory + schedule; grocery todos; constraint checks. Eval lane non-blocking. Per `capabilities/diet-and-planning.md`.
- **Acceptance:** E2E-05 structure checks green; eval optional.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01` exit 0, `make e2e-03` exit 0, `make e2e-04` exit 0. Spot-checks: seed profile allergies/dislikes/low-carb → `Plan meals for tomorrow.` Auto `diet_draft` + 10 grocery `todo_add` rows tagged `grocery`+`diet`; `check_meal_plan` clean — banned terms (peanuts, shellfish, cilantro, rice) absent from meals/grocery items; late-night calendar → quick dinner (unit). Fail-closed does not stomp task-15/e2e-05-structure verification (still PASS). INV-* intact (no weaken). **E2E-05 structure ready** for TASK-16 gate. No code fixes required.
- **Artifacts:** `src/capabilities/diet/{parse,constraints,planner,store,service,eval}.py`, `src/harness/virtual_user.py` (`run_e2e_05_structure`, NL `diet_draft` routing), `scripts/run_test_ci.py`, `artifacts/test/task-15/` (runtime; gitignored), `artifacts/test/e2e-05-structure/` (runtime; gitignored)

### TASK-16 — E2E-05 Diet → groceries
- **Phase:** 3 / T3
- **Depends on:** TASK-15
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Seed dislikes/allergies; assert absences + grocery todos.
- **Acceptance:** T3 exit for diet path.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-05` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01` exit 0, `make e2e-03` exit 0, `make e2e-04` exit 0. Spot-checks: `artifacts/test/e2e-05/verification.json` → `gate: true`, `t3_exit: true`; seed profile allergies/dislikes/low-carb → `Plan meals for tomorrow.` Auto `diet_draft` + 10 grocery `todo_add` rows tagged `grocery`+`diet`; banned terms (peanuts, shellfish, cilantro, rice) absent from meals/grocery items; eval lane score 0.9 (non-blocking). Fail-closed does not stomp task-16/e2e-05 verification (still PASS). INV-* intact (no weaken). **T3 exit** — E2E-04 + E2E-05 gates green.
- **Artifacts:** `src/harness/virtual_user.py` (`run_e2e_05`, `E2E05Result`), `scripts/run_e2e_05.py`, `Makefile` (`e2e-05`), `scripts/run_test_ci.py` (e2e layer + task-16), `scripts/test-ci.sh`, `scripts/README.md`, `artifacts/test/e2e-05/` (runtime; gitignored), `artifacts/test/task-16/` (runtime; gitignored)

### TASK-17 — Outbound voice calls + escalation ladder
- **Phase:** 4 / T4
- **Depends on:** TASK-07, TASK-11
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Mock voice provider; call tool allowlist (`INV-APPR-005`); after-call WhatsApp summary. Per `channels/voice-calls.md`.
- **Acceptance:** Mock call tests + allowlist invariant.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01` exit 0, `make e2e-03` exit 0, `make e2e-04` exit 0, `make e2e-05` exit 0. Spot-checks: call-mode blocks buy/book/self_mod_apply (`call_mode_forbidden_hard_action`) while read tools allowed; ladder WhatsApp→Android→call ordered touches; after-call WhatsApp summary queued; `INV-APPR-005` PASS. Fail-closed does not stomp task-17 verification (still PASS). INV-* intact (no weaken). No code gaps. **E2E-02 ready** for TASK-18.
- **Artifacts:** `src/channels/voice/{allowlist,provider}.py`, `src/channels/android/notifications.py`, `src/capabilities/reminders/{escalation,scheduler}.py`, `src/invariants/inv_appr_005.py`, `scripts/run_test_ci.py`, `artifacts/test/task-17/`

### TASK-18 — E2E-02 Habit escalation ladder
- **Phase:** 4 / T4
- **Depends on:** TASK-17
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** WhatsApp → Android → call ordered touches; no buy/book/self-mod on call session.
- **Acceptance:** T4 exit.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-02` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01/03/04/05` exit 0. Spot-checks: ordered channel touches WhatsApp→Android→call (`escalation-touches.json` + ladder); mid-call `buy`/`book`/`self_mod_apply` → `call_mode_forbidden_hard_action` while `memory_read` allowed (`INV-APPR-005`); after-call WhatsApp summary queued. Review fix: drop duplicate `@dataclass` on `E2E04Result`. Fail-closed does not stomp e2e-02 verification (still PASS). INV-* intact (no weaken). **T4 exit PASS** — mock voice (TASK-17) + E2E-02 ladder (TASK-18) + `INV-APPR-005` green.
- **Artifacts:** `scripts/run_e2e_02.py`, `src/harness/virtual_user.py` (`run_e2e_02`), `Makefile` (`e2e-02`), `scripts/run_test_ci.py` (gate), `artifacts/test/e2e-02/`

### TASK-19 — Bookings skill (stub portal) + hard approve
- **Phase:** 5 / T5
- **Depends on:** TASK-11, TASK-13
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Booksy-class stub; propose slots; execute only after Accept; calendar writeback; `INV-BOOK-*`. Per `capabilities/bookings.md`.
- **Acceptance:** Simulated book path + invariants.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-01/02/03/04/05` exit 0. Spot-checks: `book_count=0` until Accept; Deny → execute 0 + task `denied`; forced fail → approval/task `failed` ≠ success, no calendar/`booking_confirm` (`INV-BOOK-001/002`). Review fix: `ActionGateway.deny` syncs booking task → `denied` (Android Deny alone; no store glue). INV-* not weakened. **E2E-06 ready**; **E2E-09 ready**.
- **Artifacts:** `src/capabilities/bookings/{parse,portal,store,service}.py`, `src/invariants/inv_book_00{1,2}.py`, `src/harness/adapters.py`, `src/policy/action_gateway.py`, `src/harness/virtual_user.py`, `fixtures/browser/booksy-stub-slots.json`, `scripts/run_test_ci.py`, `artifacts/test/task-19/`

### TASK-20 — E2E-06 Booksy propose → approve → book (+ E2E-09 expiry)
- **Phase:** 5 / T5
- **Depends on:** TASK-19
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** E2E-06 accept/deny; E2E-09 ignored approval expiry.
- **Acceptance:** T5 exit.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-06` exit 0, `make e2e-09` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, sample prior e2e (`e2e-01`/`04`/`05`) exit 0. Spot-checks: Accept → `book_count=1` (second execute blocked); Deny → `book_count=0` + task `denied`; FakeClock +5h → `expired`, late Accept/execute blocked. Fail-closed does not stomp e2e-06/09/task-20 verification. INV-* intact (no weaken). No code fixes required. **T5 exit PASS** — stub portal + E2E-06 + INV-BOOK-* (+ E2E-09).
- **Artifacts:** `scripts/run_e2e_06.py`, `scripts/run_e2e_09.py`, `src/harness/virtual_user.py` (`run_e2e_06`/`run_e2e_09`), `Makefile` (`e2e-06`/`e2e-09`), `scripts/run_test_ci.py` (gate), `artifacts/test/e2e-06/`, `artifacts/test/e2e-09/`, `artifacts/test/task-20/`

### TASK-21 — Shopping skill (caps, freeze, dry-run)
- **Phase:** 6 / T6
- **Depends on:** TASK-02, TASK-11
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Propose-only then hard execute; spend caps; freeze; receipts/audit; `INV-PAY-*`. Per `capabilities/shopping.md`.
- **Acceptance:** Cap/freeze/deny paths proven.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, sample prior e2e (`e2e-01`/`04`/`06`) exit 0. Spot-checks: propose → `buy_count=0` + price 29.99 hard approve; Accept under cap → dry-run buy + receipt; freeze blocks execute with stale accepted approval (not cancelled); over cap → `spend_cap_daily` + buy=0; `INV-PAY-001/002` PASS. Fail-closed does not stomp task-21 verification (`e2e07_ready=true`). INV-* intact (no weaken). No code fixes required. **E2E-07 ready** for TASK-22.
- **Artifacts:** `src/capabilities/shopping/{parse,merchant,store,service}.py`, `src/policy/spend_caps.py`, `src/invariants/inv_pay_00{1,2}.py`, `src/policy/{action_gateway,kill_switches}.py`, `src/harness/{adapters,virtual_user}.py`, `fixtures/shopping/merchant-catalog.json`, `config/shopping.harness.json`, `scripts/run_test_ci.py`, `artifacts/test/task-21/`

### TASK-22 — E2E-07 Shopping with cap / freeze
- **Phase:** 6 / T6
- **Depends on:** TASK-21
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Full E2E-07 including deny path for merge gate.
- **Acceptance:** T6 exit; gate deny path green.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-07` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, sample prior e2e (`e2e-01`/`04`/`06`) exit 0. Spot-checks: propose price 29.99 + buy=0; Accept under cap → dry-run receipt/audit buy=1; freeze → `freeze_spending` buy=0 (stale accepted); over cap → `spend_cap_daily` buy=0; Deny → buy=0 + task denied. Fail-closed does not stomp e2e-07/task-22 verification (`t6_exit=true`). INV-PAY-001/002 intact (no weaken). No code fixes required. **T6 exit PASS** — dry-run merchant + E2E-07 + INV-PAY-*.
- **Artifacts:** `src/harness/virtual_user.py` (`run_e2e_07`, `E2E07Result`), `scripts/run_e2e_07.py`, `Makefile` (`e2e-07`), `scripts/run_test_ci.py` (gate + task-22), `scripts/test-ci.sh`, `scripts/README.md`, `artifacts/test/e2e-07/`, `artifacts/test/task-22/`

### TASK-23 — Self-modification (diff → hard approve → apply)
- **Phase:** 7 / T7
- **Depends on:** TASK-02, TASK-11
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Allowlisted paths; propose diff; apply only on Accept; freeze self-mod; secrets rejection; policy-change subtype; rollback refs; `INV-SELF-*`. Per `capabilities/self-modification.md`.
- **Acceptance:** Sample workspace fixtures; invariants green.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, sample prior e2e (`e2e-01`/`04`/`07`) exit 0. Spot-checks: outside allowlist / `.env` fail closed; propose leaves tree clean + apply tools unavailable; pending/bypass cannot apply; Accept → apply on `cursor/agent-self-*` with `rollback_ref` + audit approval id; Deny → apply=0 tree clean; `freeze_self_mod` blocks stale accepted execute; secrets rejected at propose (no approval); policy-change subtype for `src/policy/**`. Fail-closed does not stomp task-23 verification (`e2e08_ready=true`). INV-SELF-001..004 intact (no weaken). No code fixes required. **E2E-08 ready** for TASK-24.
- **Artifacts:** `artifacts/test/task-23/` (`verification.json`, `proposals.json`, `approvals.json`, `audit.json`, `workspace-status.json`, `diffs/quiet-hours.patch`, `outbound-messages.json`); `src/capabilities/selfmod/`; `src/invariants/inv_self_00{1,2,3,4}.py`; `fixtures/selfmod/`; `config/selfmod.harness.json`

### TASK-24 — E2E-08 Self-mod patch (+ deny)
- **Phase:** 7 / T7
- **Depends on:** TASK-23
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** E2E-08 accept + deny; gate deny path.
- **Acceptance:** T7 exit.
- **Result:** PASS (Agent B review) — Re-ran `make e2e-08` exit 0, `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, sample prior e2e (`e2e-01`/`04`/`07`) exit 0. Spot-checks: Accept → apply once (`apply=1`, second execute `status=executed`, re-accept blocked); Deny → apply=0 tree/reminders unchanged; INV-SELF-001..004 PASS. Fail-closed does not stomp e2e-08/task-24 verification (`t7_exit=true`). INV-SELF-* not weakened. No code fixes required. **T7 exit PASS**.
- **Artifacts:** `artifacts/test/e2e-08/` (`verification.json`, `report.json`, `proposals.json`, `approvals.json`, `audit.json`, `workspace-status.json`, `diffs/quiet-hours.patch`); `artifacts/test/task-24/`; `src/harness/virtual_user.py` (`run_e2e_08`); `scripts/run_e2e_08.py`; `Makefile` (`e2e-08`)

### TASK-25 — Polish: heartbeat, weekly review, soak, E2E-10
- **Phase:** 8 / T8
- **Depends on:** TASK-08, TASK-12, TASK-14, TASK-22, TASK-24
- **Model:** composer-2.5 (impl) + cursor-grok-4.5-high (soak/safety review)
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Morning brief / quiet policies; soak/chaos pack; restart durability E2E-10; harden injection defenses per Phase 8 roadmap.
- **Acceptance:** T8 exit criteria; nightly-oriented packs documented.
- **Result:** PASS (Agent B soak/safety review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0, `make e2e-10` exit 0, `make soak-chaos` exit 0, sample prior e2e (`e2e-01`/`08`) exit 0. Spot-checks: pause/quiet suppress morning brief + weekly review; restart → Accept once (`buy=1`, second execute/accept blocked); dup webhook → `duplicate_webhook` tools/outbound/pending once; stub-portal `APPROVE ALL` flags injection and leaves booking `pending` (`book=0`). Review fix: CI verification stamp now includes `E2E-10` in `gate_e2e` + `t8_exit`/`e2e10_ready` + task-25/e2e-10 artifact paths. Fail-closed does not stomp e2e-10/task-25 verification (`t8_exit=true`). INV-* intact (no weaken). **T8 exit PASS**.
- **Artifacts:** `src/operations/heartbeat.py`, `src/policy/{quiet_hours,injection_guard}.py`, `scripts/{run_e2e_10,run_soak_chaos}.py`, `Makefile` (`e2e-10`, `soak-chaos`), `artifacts/test/task-25/`, `artifacts/test/e2e-10/`

### TASK-26 — CI gates wiring & component-matrix mapping
- **Phase:** continuous (land early, tighten each phase)
- **Depends on:** TASK-01
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** done
- **Scope:** Wire `testing/ci-gates.md` merge gate set; map new behavior into component-matrix; ensure gate-tagged e2e list expands as phases land.
- **Acceptance:** Documented `test:ci` matches plan; B audits gaps.
- **Result:** PASS (Agent B review) — Re-ran `make test-ci` exit 0, `make test-ci-fail-closed` exit 0. Audited `docs/ci-gates.md` vs `agent-plan/testing/ci-gates.md`: four layers (unit → contract/23 INV-* → integration → e2e E2E-01..10) match `run_test_ci.py`/`test-ci.sh`. `verification.json` → `result: PASS`, `invariants` length 23, `gate_e2e` length 10, `gate_deny_paths` includes E2E-07 (`e2e-07.deny_buys_nothing`) + E2E-08 (`e2e-08.deny_leaves_tree_unchanged`). Deny stamps: `e2e-07` → `buy_count_after_deny: 0`; `e2e-08` → `tree_clean_after_deny: true`. INV-* intact (no weaken). No code fixes required.
- **Artifacts:** `docs/ci-gates.md`, `scripts/run_test_ci.py`, `README.md`, `scripts/README.md`, `artifacts/test/README.md`

---

## Dispatch log

| Time (UTC) | Task | Agent | Model | Role | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-08-08 21:46 | TASK-00 | subagent-A | composer-2.5 | implement | First dispatch — bootstrap layout |
| 2026-08-08 21:50 | TASK-00 | Agent A | composer-2.5 | implement | Bootstrap complete — layout + test:ci stub; status → review |
| 2026-08-08 21:52 | TASK-00 | Agent B | composer-2.5 | review | PASS — checklist verified; README make target fix; status → done |
| 2026-08-08 21:53 | TASK-01 | subagent-A | cursor-grok-4.5-high | implement | T0 harness: fake clock, INV runner, fail-closed test:ci |
| 2026-08-08 21:55 | TASK-01 | Agent A | cursor-grok-4.5-high | implement | T0 complete — test:ci + fail-closed proof; status → review |
| 2026-08-08 21:50 | TASK-01 | Agent B | cursor-grok-4.5-high | review | PASS — fail-closed re-verified; test-ci.sh set -e status fix; status → done |
| 2026-08-08 21:56 | TASK-02 | subagent-A | cursor-grok-4.5-high | implement | Approval matrix + kill switches + INV-APPR/KILL/AUDIT |
| 2026-08-08 21:58 | TASK-02 | Agent A | cursor-grok-4.5-high | implement | Trust core complete — INV-APPR/KILL/AUDIT green; status → review |
| 2026-08-08 21:54 | TASK-02 | Agent B | cursor-grok-4.5-high | review | PASS — re-ran test-ci + fail-closed; INV-APPR/KILL/AUDIT + spot-checks; status → done |
| 2026-08-08 21:59 | TASK-03 | subagent-A | cursor-grok-4.5-high | implement | Full WhatsApp ingress allowlist + mock transport + adversarial INV-INGRESS |
| 2026-08-08 22:00 | TASK-03 | Agent A | cursor-grok-4.5-high | implement | Ingress hardened — mock transport + INV-INGRESS-001/002 adversarial + 003 scaffold; status → review |
| 2026-08-08 22:00 | TASK-03 | Agent B | cursor-grok-4.5-high | review | PASS — re-ran test-ci + fail-closed; @newsletter non-DM fix; status → done |
| 2026-08-08 22:02 | TASK-04 | subagent-A | composer-2.5 | implement | Personal memory profile template + R/W integration |
| 2026-08-08 22:05 | TASK-04 | Agent A | composer-2.5 | implement | Memory store + INV-MEM-001 + integration; status → review |
| 2026-08-08 22:06 | TASK-04 | Agent B | composer-2.5 | review | PASS — re-ran test-ci + fail-closed; secrets/fixture/persistence spot-checks; status → done |
| 2026-08-08 22:08 | TASK-05 | subagent-A | composer-2.5 | implement | Hosting/Gateway config + approval store reboot durability |
| 2026-08-08 22:06 | TASK-05 | Agent A | composer-2.5 | implement | Durable approvals + E2E-10 prep tests; status → review |
| 2026-08-08 22:06 | TASK-05 | Agent B | composer-2.5 | review | PASS — re-ran test-ci + fail-closed; restart/accept-once spot-checks; status → done |
| 2026-08-08 22:10 | TASK-06 | subagent-A | cursor-grok-4.5-high | implement | STT stub + audio fixtures + INV-INGRESS-003 transcription path |
| 2026-08-08 22:12 | TASK-06 | Agent A | cursor-grok-4.5-high | implement | STT+TTS+pipeline wired; INV-INGRESS-003 full; status → review |
| 2026-08-08 22:15 | TASK-06 | Agent B | cursor-grok-4.5-high | review | PASS — re-ran test-ci + fail-closed; duration bound fix; status → done |
| 2026-08-08 22:16 | TASK-07 | subagent-A | cursor-grok-4.5-high | implement | Reminders + habits with fake clock |
| 2026-08-08 22:17 | TASK-07 | Agent A | cursor-grok-4.5-high | implement | Reminders/habits complete — FakeClock fire + confirm; status → review |
| 2026-08-08 22:20 | TASK-07 | Agent B | cursor-grok-4.5-high | review | PASS — re-ran test-ci + fail-closed; parse/fire/auto spot-checks; task-07 artifact stomp fix; status → done |
| 2026-08-08 22:21 | TASK-08 | subagent-A | cursor-grok-4.5-high | implement | E2E-01 Virtual User voice reminder journey |
| 2026-08-08 22:25 | TASK-08 | Agent A | cursor-grok-4.5-high | implement | E2E-01 gate green — VirtualUser + test:ci e2e layer; status → review |
| 2026-08-08 22:28 | TASK-08 | Agent B | cursor-grok-4.5-high | review | PASS — e2e-01/test-ci/fail-closed exit 0; due+no-hard spot-checks; T1 exit; status → done |
| 2026-08-08 22:29 | TASK-09 | subagent-A | composer-2.5 | implement | Luna/Terra-Sol models router stubs |
| 2026-08-08 22:32 | TASK-09 | Agent A | composer-2.5 | implement | Router stubs + INV-MODEL-001/002 + task-09 artifacts; status → review |
| 2026-08-08 22:35 | TASK-09 | Agent B | composer-2.5 | review | PASS — test-ci/fail-closed/e2e-01 exit 0; Luna/Sol spot-checks; status → done |
| 2026-08-08 22:36 | TASK-10 | subagent-A | composer-2.5 | implement | Todos store + Android projection API doubles |
| 2026-08-08 22:40 | TASK-10 | Agent A | composer-2.5 | implement | Todo store + Android API doubles + E2E-03 prep; status → review |
| 2026-08-08 22:42 | TASK-10 | Agent B | composer-2.5 | review | PASS — test-ci/fail-closed/e2e-01 exit 0; todo/Android/dedup spot-checks; dup run_e2e_03 fix; status → done |
| 2026-08-08 22:43 | TASK-11 | subagent-A | cursor-grok-4.5-high | implement | Android approval inbox + Virtual User Accept/Deny |
| 2026-08-08 22:36 | TASK-11 | Agent A | cursor-grok-4.5-high | implement | Android inbox + soft-confirm hooks; T2 exit; status → review |
| 2026-08-08 22:36 | TASK-11 | Agent B | cursor-grok-4.5-high | review | PASS — test-ci/fail-closed/e2e-01 exit 0; Accept/Deny/Edit + create_count=0 spot-checks; T2 exit; status → done |
| 2026-08-08 22:48 | TASK-12 | subagent-A | composer-2.5 | implement | E2E-03 gate-tagged todo WhatsApp → Android; status → review |
| 2026-08-08 22:40 | TASK-12 | Agent B | composer-2.5 | review | PASS — e2e-03/e2e-01/test-ci/fail-closed exit 0; gate:true artifacts; T2 exit; status → done |
| 2026-08-08 22:52 | TASK-13 | subagent-A | cursor-grok-4.5-high | implement | Calendar R/W + soft confirm + conflicts |
| 2026-08-08 22:45 | TASK-13 | Agent A | cursor-grok-4.5-high | implement | Calendar store + soft confirm NL path; status → review |
| 2026-08-08 22:50 | TASK-13 | Agent B | cursor-grok-4.5-high | review | PASS — test-ci/fail-closed/e2e-01/e2e-03 exit 0; create_count/Deny/conflict spot-checks; E2E-04 ready; status → done |
| 2026-08-08 22:55 | TASK-14 | subagent-A | composer-2.5 | implement | E2E-04 gate calendar soft confirm accept/deny |
| 2026-08-08 23:00 | TASK-14 | Agent A | composer-2.5 | implement | E2E-04 gate + test:ci e2e layer; status → review |
| 2026-08-08 23:05 | TASK-14 | Agent B | composer-2.5 | review | PASS — e2e-04/e2e-01/e2e-03/test-ci/fail-closed exit 0; gate:true + accept/deny create counts; status → done |
| 2026-08-08 23:06 | TASK-15 | subagent-A | composer-2.5 | implement | Diet planning v1 + grocery todos from memory |
| 2026-08-08 23:12 | TASK-15 | Agent A | composer-2.5 | implement | Diet v1 complete — constraints + grocery todos + E2E-05 structure; status → review |
| 2026-08-08 23:15 | TASK-15 | Agent B | composer-2.5 | review | PASS — test-ci/fail-closed/e2e-01/03/04 exit 0; banned-absent + grocery todo spot-checks; E2E-05 ready; status → done |
| 2026-08-08 23:16 | TASK-16 | subagent-A | composer-2.5 | implement | E2E-05 diet → groceries journey |
| 2026-08-08 23:55 | TASK-16 | Agent A | composer-2.5 | implement | E2E-05 gate + test:ci e2e layer; T3 exit ready; status → review |
| 2026-08-08 23:58 | TASK-16 | Agent B | composer-2.5 | review | PASS — e2e-05/test-ci/fail-closed/e2e-01/03/04 exit 0; gate:true + banned-absent spot-checks; T3 exit; status → done |
| 2026-08-09 00:00 | TASK-17 | subagent-A | cursor-grok-4.5-high | implement | Mock voice calls + INV-APPR-005 + escalation |
| 2026-08-09 00:15 | TASK-17 | Agent A | cursor-grok-4.5-high | implement | Mock voice + INV-APPR-005 + ladder; status → review |
| 2026-08-08 23:05 | TASK-17 | Agent B | cursor-grok-4.5-high | review | PASS — test-ci/fail-closed/e2e-01/03/04/05 exit 0; call-mode + ladder + summary spot-checks; E2E-02 ready; status → done |
| 2026-08-09 00:10 | TASK-18 | subagent-A | cursor-grok-4.5-high | implement | E2E-02 habit escalation ladder |
| 2026-08-09 00:25 | TASK-18 | Agent A | cursor-grok-4.5-high | implement | E2E-02 gate + test:ci; T4 exit ready; status → review |
| 2026-08-09 00:35 | TASK-18 | Agent B | cursor-grok-4.5-high | review | PASS — e2e-02/test-ci/fail-closed/prior e2e exit 0; ordered touches + allowlist spot-checks; T4 exit; status → done |
| 2026-08-09 00:40 | TASK-19 | subagent-A | cursor-grok-4.5-high | implement | Bookings stub portal + hard approve + INV-BOOK |
| 2026-08-09 00:55 | TASK-19 | Agent A | cursor-grok-4.5-high | implement | Stub portal + INV-BOOK-001/002 + writeback; status → review |
| 2026-08-09 01:10 | TASK-19 | Agent B | cursor-grok-4.5-high | review | PASS — test-ci/fail-closed/prior e2e exit 0; deny writeback fix; E2E-06 ready; status → done |
| 2026-08-09 01:12 | TASK-20 | subagent-A | cursor-grok-4.5-high | implement | E2E-06 + E2E-09 booking journeys |
| 2026-08-09 01:30 | TASK-20 | Agent A | cursor-grok-4.5-high | implement | E2E-06 gate + E2E-09 expiry; T5 exit ready; status → review |
| 2026-08-08 23:19 | TASK-20 | Agent B | cursor-grok-4.5-high | review | PASS — e2e-06/09/test-ci/fail-closed/prior e2e exit 0; accept-once/deny-0/expiry spot-checks; T5 exit; status → done |
| 2026-08-09 01:25 | TASK-21 | subagent-A | cursor-grok-4.5-high | implement | Shopping caps/freeze/dry-run + INV-PAY |
| 2026-08-08 23:25 | TASK-21 | Agent A | cursor-grok-4.5-high | implement | Shopping dry-run + INV-PAY-001/002 + caps/freeze; status → review |
| 2026-08-08 23:26 | TASK-21 | Agent B | cursor-grok-4.5-high | review | PASS — test-ci/fail-closed/sample e2e exit 0; propose/accept/freeze/cap/INV-PAY spot-checks; E2E-07 ready; status → done |
| 2026-08-09 01:40 | TASK-22 | subagent-A | cursor-grok-4.5-high | implement | E2E-07 shopping cap/freeze/deny gate |
| 2026-08-09 02:00 | TASK-22 | Agent A | cursor-grok-4.5-high | implement | E2E-07 gate + test:ci; T6 exit ready; status → review |
| 2026-08-08 23:31 | TASK-22 | Agent B | cursor-grok-4.5-high | review | PASS — e2e-07/test-ci/fail-closed/sample e2e exit 0; accept/freeze/cap/deny spot-checks; T6 exit; status → done |
| 2026-08-09 01:55 | TASK-23 | subagent-A | cursor-grok-4.5-high | implement | Self-mod allowlist + hard approve apply + INV-SELF |
| 2026-08-09 02:15 | TASK-23 | Agent A | cursor-grok-4.5-high | implement | Self-mod + INV-SELF-001..004 + E2E-08 ready; status → review |
| 2026-08-08 23:45 | TASK-23 | Agent B | cursor-grok-4.5-high | review | PASS — test-ci/fail-closed/sample e2e exit 0; allowlist/Accept/freeze/secrets/rollback_ref/INV-SELF spot-checks; E2E-08 ready; status → done |
| 2026-08-09 02:10 | TASK-24 | subagent-A | cursor-grok-4.5-high | implement | E2E-08 self-mod accept+deny gate |
| 2026-08-09 02:30 | TASK-24 | Agent A | cursor-grok-4.5-high | implement | E2E-08 gate + test:ci; T7 exit ready; status → review |
| 2026-08-08 23:44 | TASK-24 | Agent B | cursor-grok-4.5-high | review | PASS — e2e-08/test-ci/fail-closed/sample e2e exit 0; accept-once/deny/INV-SELF spot-checks; T7 exit; status → done |
| 2026-08-09 02:25 | TASK-25 | subagent-A | composer-2.5 | implement | Polish: heartbeat, soak, E2E-10 durability |
| 2026-08-08 23:50 | TASK-25 | Agent A | composer-2.5 | implement | T8 polish complete — heartbeat/soak/E2E-10; status → review |
| 2026-08-08 23:55 | TASK-25 | Agent B | cursor-grok-4.5-high | review | PASS — soak/e2e-10/spot-checks; CI t8_exit stamp fix; T8 exit; status → done |
| 2026-08-09 02:40 | TASK-26 | subagent-A | composer-2.5 | implement | CI gates audit + component-matrix mapping docs |
| 2026-08-09 02:55 | TASK-26 | Agent A | composer-2.5 | implement | GATE_MAP docs + verification stamp; status → review |
| 2026-08-09 03:00 | TASK-26 | Agent B | composer-2.5 | review | PASS — test-ci/fail-closed exit 0; ci-gates audit + E2E-07/08 deny paths; status → done |
| 2026-08-09 00:05 | PROD-wave | planner | — | dispatch | Parallel PROD-01..09 in_progress; cheapest cloud = Oracle Free / Hetzner; full always-on (not stub) |
| 2026-08-09 00:10 | PROD-04 | Agent A | composer-2.5 | implement | OpenClaw skills pack memory/reminders/todos/heartbeat; status → review |
| 2026-08-09 00:01 | PROD-02 | Agent A | cursor-grok-4.5-high | implement | Production OpenClaw Codex/Luna + WhatsApp Baileys templates; status → review |
| 2026-08-09 00:15 | PROD-01 | Agent A | composer-2.5 | implement | Docker compose + deploy runbook + systemd + backup scripts; status → review |
| 2026-08-09 00:04 | PROD-03 | Agent A | cursor-grok-4.5-high | implement | Production STT+TTS config + inbound TTS; fixture STT kept; status → review |
| 2026-08-09 00:20 | PROD-07 | Agent A | cursor-grok-4.5-high | implement | Twilio/Telnyx voice production + INV-APPR-005 policy; status → review |

---



## Rules for sub-agents (mandatory)

1. Read the relevant `agent-plan/**` leaf docs before coding.
2. Follow autonomous verification loop in `testing/autonomous-agent-process.md`.
3. Prefer mocks in **CI/harness**; for PROD-* tasks ship **production OpenClaw config/skills/deploy** as first-class (no new stub-only production paths). Fake the clock in tests; assert state not prose.
4. Write artifacts under `artifacts/test/<task-or-flow>/`.
5. Update **this file**: set Status, Result (PASS/FAIL/BLOCKED + 3–8 lines), Artifacts paths, and append Dispatch log if needed.
6. Commit on the working branch with a clear message; push when instructed by planner workflow.
7. Do not weaken or delete INV-* tests to go green.
8. Do not install packages via pip/apt/npm/conda — ask planner/user if deps are missing (user rule).
9. No live WhatsApp/Twilio/Booksy/money in CI.
10. Planner owns prioritization; do not start dependent tasks early unless planner re-dispatches.

---

## Current focus

**Wave PROD (full always-on app — not stubs):** parallel finish for real OpenClaw Gateway deploy + production channel/skill wiring. Harness CI stays green; production path is first-class.

**Cheapest cloud deploy (answered):** Oracle Cloud Always Free ARM VM if available, else Hetzner CX22-class VPS (~€4–5/mo). Always-on Docker/systemd OpenClaw Gateway; persist `~/.openclaw`; Luna via Codex subscription. Not serverless.

---

## Production wave — full application (parallel)

> Goal: ship a deployable always-on personal agent (OpenClaw + Luna + WhatsApp + Android + STT/TTS + calendar + calls + bookings + shopping + self-mod), not harness-only stubs. Keep `make test-ci` green. **No package installs** in agents — write Docker/install scripts the operator runs.

### PROD-01 — Cloud deploy: Docker Compose + cheap VPS runbook
- **Depends on:** —
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** review
- **Scope:** Full always-on deploy (not minimal). `deploy/docker-compose.yml` (or equivalent) for OpenClaw Gateway + volumes for credentials/memory/approvals; `docs/deploy.md` covering Oracle Always Free ARM **and** Hetzner CX22; systemd alternative; backup/restore of `~/.openclaw`; reboot survival; HTTPS/tunnel notes for later Twilio webhooks. Operator checklist from zero → Gateway up.
- **Acceptance:** Operator can follow docs to bring Gateway up on a small VPS; compose validated structurally (agents cannot install OpenClaw if blocked — document exact commands).
- **Result:** PASS (Agent A) — Official OpenClaw image compose (`ghcr.io/openclaw/openclaw`) with `~/.openclaw` + workspace + auth-profile bind mounts, `restart: unless-stopped`, loopback-default ports. Operator scripts: `setup-docker.sh`, `backup-openclaw.sh`, `install-systemd.sh`. systemd unit template for non-Docker. `docs/deploy.md` covers Oracle ARM + Hetzner CX22, UFW, reboot survival, backup/restore cron, HTTPS/Twilio notes, zero→up checklist. CI structural checks: `integration.deploy.prod01_*` (no Docker install).
- **Artifacts:** `deploy/docker-compose.yml`, `deploy/.env.example`, `deploy/setup-docker.sh`, `deploy/backup-openclaw.sh`, `deploy/openclaw-gateway.service`, `deploy/install-systemd.sh`, `deploy/README.md`, `docs/deploy.md`, `scripts/run_test_ci.py` (`_run_prod01_deploy_checks`)

### PROD-02 — OpenClaw production config: Codex/Luna + WhatsApp allowlist
- **Depends on:** —
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** review
- **Scope:** Production `config/openclaw/` (or `config/production/`) — Codex auth profile intent, **Luna default**, Terra/Sol escalation hooks, WhatsApp channel (Baileys) `allowFrom` your number, groups disabled, DM policy, media/STT pipeline hooks. No stub transport as the production path. Align with OpenClaw docs (WhatsApp Web QR login).
- **Acceptance:** Copy-ready production config templates + README; harness still uses mocks for CI.
- **Result:** PASS (Agent A implement) — Added production OpenClaw templates under `config/openclaw/`: Codex/ChatGPT subscription auth order intent, default model `openai/gpt-5.6-luna` with Terra/Sol fallbacks + `escalation.hooks.json` aligned to models-and-credits + harness router, WhatsApp Web (Baileys) `dmPolicy: allowlist` / `allowFrom` placeholder / `groupPolicy: disabled` / self-chat DM baseline, `tools.media.audio` STT-before-agent + inbound TTS. README covers `openclaw channels login --channel whatsapp` QR flow. Harness/CI mocks unchanged. `make test-ci` green.
- **Artifacts:** `config/openclaw/openclaw.production.json5`, `config/openclaw/escalation.hooks.json`, `config/openclaw/README.md`, `config/README.md`, `README.md`, `.gitignore`

### PROD-03 — STT + TTS production providers (full voice path)
- **Depends on:** —
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** review
- **Scope:** Production transcription + TTS provider config and skill/wiring for OpenClaw media path. Primary: OpenAI transcription (`gpt-4o-transcribe` / mini) with Whisper fallback notes; TTS for inbound-audio replies. Env templates for keys. Keep fixture STT in harness for CI.
- **Acceptance:** Documented + config-wired production STT/TTS; CI fixtures unchanged.
- **Result:** PASS (Agent A implement) — Production voice path additive: `config/production/openclaw.voice.json` (OpenAI `gpt-4o-transcribe` → mini + `messages.tts.auto: inbound` / `gpt-4o-mini-tts`), Whisper CLI fallback fragment + notes, `voice.env.example` for `OPENAI_API_KEY`. Loader `src/intelligence/transcription/production.py` (structural only, no live HTTP). Aligned `agent-plan/intelligence/transcription.md` + `docs/production-voice.md`; enriched `config/openclaw/openclaw.production.json5` TTS providers. Fixture `SttStub` remains CI default (`unit.prod03.*`). Ready for Agent B.
- **Artifacts:** `config/production/openclaw.voice.json`, `config/production/openclaw.voice.whisper-fallback.json`, `config/production/voice.env.example`, `config/production/README.md`, `docs/production-voice.md`, `src/intelligence/transcription/production.py`, `agent-plan/intelligence/transcription.md`


### PROD-04 — OpenClaw skills pack: memory, reminders, todos, heartbeat
- **Depends on:** —
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** review
- **Scope:** Package production OpenClaw skills under `src/skills/` (or OpenClaw skills dir convention) for memory R/W, reminders/habits, todos, morning brief/weekly review — real skill manifests that Gateway can load, not only Python harness services. Map harness logic → skill interfaces.
- **Acceptance:** Skills loadable by OpenClaw layout; unit/contract still pass via harness adapters.
- **Result:** Agent A — Four AgentSkills-compatible skills (`personal-memory`, `reminders-habits`, `personal-todos`, `heartbeat-ops`) with `SKILL.md` + harness-map references; `src/tools/{schemas.json,registry.py,bridge.py}`; `ActionGateway` real adapters for `memory_read`/`memory_update`/`todo_read`/reminder manage/heartbeat tools; `config/openclaw/skills-production.json5` + merge into `config/production/openclaw.skills.snippet.json`; `make test-ci` + `make test-ci-fail-closed` exit 0; unit checks `unit.skill_pack.*`.
- **Artifacts:** `src/skills/`, `src/tools/`, `config/openclaw/skills-production.json5`, `config/production/openclaw.skills.snippet.json`, `src/policy/{action_gateway,approvals}.py`, `scripts/run_test_ci.py`

### PROD-05 — Android companion + approvals production wiring
- **Depends on:** —
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** review
- **Scope:** Production pairing docs + config for OpenClaw Android node: todos sync, approval inbox (Accept/Deny/Edit), kill switches on Status screen, self-mod approval cards. Full always-on control plane — not API doubles alone.
- **Acceptance:** Operator checklist to pair phone; config templates; CI doubles remain for gate tests.
- **Result:** Agent A — Production pairing runbook + operator checklist (`docs/android-pairing.md`); `config/android.example.yaml` (todos, Accept/Deny/Edit inbox, Status kill switches, self-mod cards); `config/android.harness.json` keeps CI doubles; `AndroidStatusApi` + self-mod card badges on inbox projection; plan leaf aligned. Unit checks `unit.android_status.*`, `unit.android.prod05_*`, `unit.android_approval.self_mod_card_fields`. Ready for Agent B.
- **Artifacts:** `docs/android-pairing.md`, `config/android.example.yaml`, `config/android.harness.json`, `config/gateway.example.yaml`, `config/backup.example.json`, `config/README.md`, `agent-plan/channels/{android-companion,index}.md`, `agent-plan/operations/hosting.md`, `src/channels/android/{status,approvals,projection,__init__}.py`, `scripts/run_test_ci.py`

### PROD-06 — Google Calendar production adapter (soft confirm)
- **Depends on:** —
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** in_progress
- **Scope:** Real Google Calendar OAuth/config + soft-confirm write path for production; in-memory calendar remains harness default. Conflict-aware suggestions preserved.
- **Acceptance:** Production adapter + secrets template; harness calendar tests green.
- **Result:** _(agent)_
- **Artifacts:** _(agent)_

### PROD-07 — Twilio (or Telnyx) voice calls production
- **Depends on:** —
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** review
- **Scope:** Full call path config: provider credentials template, webhook URL, outbound allowlist, INV-APPR-005 tool allowlist in production skill policy, after-call WhatsApp summary. Mock provider stays for CI.
- **Acceptance:** Production voice plugin/config + runbook; CI mock path green.
- **Result:** PASS (Agent A implement) — Production Twilio/Telnyx path: `config/production/openclaw.voice-call.json` + `voice-call.env.example` (webhook URL notes), outbound operator allowlist, `src/skills/voice-calls` + `call-mode.policy.json` (`INV-APPR-005` — no buy/book/self_mod_apply mid-call), after-call WhatsApp summary via `ProductionVoiceProvider`/`MockVoiceProvider`. Runbook `docs/voice-calls.md`; plan leaf aligned. CI stays on mock (`unit.voice.prod07_*` + existing mock/INV-APPR-005).
- **Artifacts:** `config/production/{openclaw.voice-call.json,voice-call.env.example,call-mode.policy.json}`, `src/skills/voice-calls/`, `src/channels/voice/{config,production}.py`, `src/policy/call_mode.py`, `docs/voice-calls.md`, `agent-plan/channels/voice-calls.md`, `config/gateway.example.yaml`, `scripts/run_test_ci.py`

### PROD-08 — Bookings + shopping production skills (hard approve)
- **Depends on:** —
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** in_progress
- **Scope:** Production Booksy-class browser skill config + shopping merchant adapters behind hard approve, caps, freeze; dry-run default with live flag documented. Stub portal remains CI-only.
- **Acceptance:** Production skill configs + safety flags; INV-BOOK/PAY still gate CI.
- **Result:** _(agent)_
- **Artifacts:** _(agent)_

### PROD-09 — Self-mod production path + allowlist for this repo
- **Depends on:** —
- **Model:** cursor-grok-4.5-high
- **Agents:** A implement · B review
- **Status:** review
- **Scope:** Production self-mod skill targeting this repo’s allowlisted paths; hard approve; freeze self-mod; policy-change subtype; rollback refs. Fixture workspace stays for CI.
- **Acceptance:** Allowlist for real repo paths + production skill; INV-SELF green in CI.
- **Result:** PASS (Agent A implement) — Production allowlist `config/selfmod.allowlist.production.json` covers `src/skills/**`, `docs/**`, `config/**`, `agent-plan/**`, `scripts/**`, `tests/**`, `src/policy/**` and forbids secrets/local/data/`.env`. OpenClaw skill `src/skills/self-modification/SKILL.md` + `config/selfmod.production.json` encode hard approve, freeze_self_mod, policy-change subtype, rollback refs / `cursor/agent-self-*`. Loader `src/capabilities/selfmod/production.py` + CI unit checks `unit.selfmod.prod09_*`. `make test-ci` / `make test-ci-fail-closed` / `make e2e-08` green; INV-SELF-001..004 intact on fixtures. Agent-plan `self-modification.md` aligned. Ready for Agent B review.
- **Artifacts:** `config/selfmod.allowlist.production.json`, `config/selfmod.production.json`, `config/selfmod.harness.json`, `src/skills/self-modification/SKILL.md`, `src/skills/README.md`, `src/capabilities/selfmod/production.py`, `agent-plan/capabilities/self-modification.md`, `artifacts/test/prod-09/` (`verification.json`, `report.json`, `production-config.json`, `allowlist.json`)

### PROD-10 — Operator go-live checklist + secrets inventory
- **Depends on:** PROD-01 (soft)
- **Model:** composer-2.5
- **Agents:** A implement · B review
- **Status:** queued
- **Scope:** Single `docs/go-live.md`: ordered enablement WhatsApp→STT→Android→Calendar→Calls→Book/Buy→Self-mod; secrets inventory (Codex, STT, Twilio, Google, etc.); cost expectations; what must be purchased vs subscription.
- **Acceptance:** One doc an operator can follow end-to-end on phone.
- **Result:** _(agent)_
- **Artifacts:** _(agent)_

---
