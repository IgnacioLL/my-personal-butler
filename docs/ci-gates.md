# CI gates map

Authoritative wiring reference for merge gate `test:ci`. Plan source: [`agent-plan/testing/ci-gates.md`](../agent-plan/testing/ci-gates.md). Component depth: [`agent-plan/testing/component-matrix.md`](../agent-plan/testing/component-matrix.md).

## Merge gate entrypoints

| Command | Role |
| --- | --- |
| `./scripts/test-ci.sh` or `make test-ci` | Happy path — must exit 0 |
| `./scripts/test-ci.sh --break-invariant` | Deliberately breaks `INV-INGRESS-*` — must exit ≠ 0 |
| `make test-ci-fail-closed` | Wraps broken mode; exits 0 only when CI correctly rejects |

Implementation: [`scripts/run_test_ci.py`](../scripts/run_test_ci.py) layers → [`scripts/test-ci.sh`](../scripts/test-ci.sh).

## Layer order (fail-closed)

1. **unit** — parsers, tiers, fake clock, stub registries
2. **contract** — all discoverable `INV-*` via [`src/harness/inv_runner.py`](../src/harness/inv_runner.py)
3. **integration** — harness profile doubles (ingress, trust core, capability NL paths, Virtual User hooks)
4. **e2e** — gate-tagged Virtual User journeys (`gate: true` in flow artifacts)

Any layer `FAIL` → aggregate `test:ci` `FAIL` (non-zero exit).

## Invariant coverage (`INV-*`)

All modules under `src/invariants/` with `INV_ID` + `check()` run in the contract layer. Current set (23):

| ID | Area | Component matrix row |
| --- | --- | --- |
| `INV-T0-CLOCK` | Harness fake clock | (scaffolding) |
| `INV-INGRESS-001` | Allowlisted DM only | WhatsApp allowlist / routing |
| `INV-INGRESS-002` | Groups off | WhatsApp allowlist / routing |
| `INV-INGRESS-003` | Voice → transcript or clarify | Voice note → STT → turn |
| `INV-MEM-001` | No secrets in memory files | Memory read/write |
| `INV-MODEL-001` | Luna default routing | Models router |
| `INV-MODEL-002` | Terra/Sol escalation signals | Models router |
| `INV-APPR-001` | No hard execute without accept | Approval matrix engine |
| `INV-APPR-002` | Denied/expired cannot execute | Approval matrix engine |
| `INV-APPR-003` | Soft confirm before calendar write | Calendar read/write |
| `INV-APPR-004` | Cancel pending | Approval matrix engine |
| `INV-APPR-005` | Call-mode tool allowlist | Outbound calls |
| `INV-KILL-001` | Pause agent stops cron | Kill switches |
| `INV-KILL-002` | Freeze spending / self-mod | Kill switches |
| `INV-AUDIT-001` | Gated writes audited | Approval matrix engine |
| `INV-BOOK-001` | No book until accept | Bookings |
| `INV-BOOK-002` | Failed booking ≠ success | Bookings |
| `INV-PAY-001` | Freeze blocks stale accepted buy | Shopping |
| `INV-PAY-002` | Spend cap enforcement | Shopping |
| `INV-SELF-001` | Path allowlist | Self-modification |
| `INV-SELF-002` | Propose leaves tree clean | Self-modification |
| `INV-SELF-003` | Apply only after accept | Self-modification |
| `INV-SELF-004` | Secrets rejected at propose | Self-modification |

**Policy:** do not weaken or skip any `INV-*` to go green. Fail-closed proof uses `--break-invariant` on ingress only.

## Gate E2E flows

### Minimum required (ci-gates.md)

| Flow | Gate | Deny path in merge gate | Phase exit |
| --- | --- | --- | --- |
| E2E-01 | ● | — | T1 |
| E2E-03 | ● | — | T2 |
| E2E-04 | ● | `e2e-04.deny_creates_nothing` | T3 |
| E2E-07 | ● | `e2e-07.deny_buys_nothing` | T6 |
| E2E-08 | ● | `e2e-08.deny_leaves_tree_unchanged` | T7 |

### Full merge gate set (landed through T8)

| Flow | Gate | Deny path | Notes |
| --- | --- | --- | --- |
| E2E-01 | ● | — | Voice reminder |
| E2E-02 | ● | — | Habit escalation ladder (T4) |
| E2E-03 | ● | — | Todo → Android |
| E2E-04 | ● | ● | Calendar soft confirm |
| E2E-05 | ● | — | Diet → groceries; eval score **non-blocking** (`gate: false`) |
| E2E-06 | ● | ● | Booksy propose → approve → book |
| E2E-07 | ● | ● | Shopping cap / freeze / deny |
| E2E-08 | ● | ● | Self-mod accept + deny |
| E2E-09 | ● | — | Ignored hard approval expiry (T5) |
| E2E-10 | ● | — | Restart mid-flight durability (T8) |

Runner: `run_e2e()` in `scripts/run_test_ci.py` → `src/harness/virtual_user.py` (`run_e2e_01` … `run_e2e_10`). Per-flow: `make e2e-NN` / `scripts/run_e2e_NN.py`.

Stamp field `gate_e2e` in `artifacts/test/ci/verification.json` lists all ten flows on happy-path CI.

## Component matrix → CI mapping

| Component | U | C (INV) | I | E (gate) | Deferred (intentional) |
| --- | --- | --- | --- | --- | --- |
| WhatsApp allowlist / routing | ● | INGRESS-001/002 | ingress_stub, mock transport | E2E-03 | Live-smoke (L) |
| Voice note → STT → turn | ● | INGRESS-003 | transcription.* | E2E-01 | WER eval (Ev) |
| TTS reply mode | ● | — | tts_inbound_mode | — | Full TTS e2e optional |
| Outbound calls | ● | APPR-005 | voice.escalation_* | E2E-02 | Live Twilio (L) |
| Android todos sync | ● | — | todo.* | E2E-03 | — |
| Android approvals UI | ● | APPR-001..004 | android_approval.* | E2E-04/06/07/08 deny | UI snapshots (L) |
| Models router | ● | MODEL-001/002 | models.* | — | No dedicated e2e (router in flows) |
| Transcription pipeline | ● | INGRESS-003 | transcription.* | E2E-01 | Eval WER (Ev) |
| Memory read/write | ● | MEM-001 | memory.* | (profile in E2E-05) | Memory eval (Ev) |
| Reminders / cron | ● | KILL-001 | reminder.* | E2E-01 | — |
| Habits escalation | ● | APPR-005 | voice.escalation_* | E2E-02 | — |
| Todos | ● | — | todo.* | E2E-03 | — |
| Calendar read/write | ● | APPR-003 | calendar.* | E2E-04 | Live calendar (L) |
| Diet planning | ● | — | diet.* | E2E-05 | Prose quality eval (Ev, non-gate) |
| Bookings | ● | BOOK-001/002 | booking.* | E2E-06, E2E-09 | Prod portal (L) |
| Shopping | ● | PAY-001/002 | shopping.* | E2E-07 | Real money (never in CI) |
| Self-modification | ● | SELF-001..004 | selfmod.* | E2E-08 | Prod apply (hard approve only) |
| Approval matrix engine | ● | APPR-*, AUDIT-001 | trust_core.* | all hard-gated e2e | — |
| Kill switches | ● | KILL-* | reminder.pause, shopping.freeze | E2E-07 freeze path | — |
| Hosting reboot resilience | — | — | gateway restart hooks | E2E-10 | VPS live (L) |

● = exercised in merge gate today. ○ / blank = optional per matrix or deferred below.

## Intentional deferrals (not merge gate)

| Item | Rationale | Where exercised |
| --- | --- | --- |
| `make soak-chaos` | Nightly soak/chaos per ci-gates.md | `scripts/run_soak_chaos.py`; TASK-25 artifacts |
| E2E-05 eval lane | Prose quality; structure gated, score optional | `e2e-05.eval_score` (`gate: false`) |
| Live-smoke (WhatsApp audio, Twilio) | Manual / flagged; never blocking merge | ci-gates.md § Live-smoke |
| Staged adapter tests with real merchants | No real money in CI | ci-gates.md § Nightly |
| TTS voice beauty | Assert mode rules only | component-matrix TTS row |

## Artifacts

Happy-path CI writes:

- `artifacts/test/ci/{report.json,report.md,verification.json}`
- `artifacts/test/ci/{unit,contract,integration,e2e}/report.json`
- `artifacts/test/e2e-NN/` per gate flow

See [`artifacts/test/README.md`](../artifacts/test/README.md).

## Agent B audit checklist

1. `git pull` on working branch
2. `make test-ci` → exit 0; `artifacts/test/ci/verification.json` → `result: PASS`, `invariants` length 23, `gate_e2e` length 10
3. `make test-ci-fail-closed` → exit 0 (inner CI failed on broken INV)
4. Spot-check deny stamps: `e2e-07.verification.json` → `buy_count_after_deny: 0`; `e2e-08.verification.json` → `tree_clean_after_deny: true`
5. Confirm no `INV-*` removed or weakened vs this map
