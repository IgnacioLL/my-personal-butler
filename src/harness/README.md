# Harness (T0+)

| Module | Role |
| --- | --- |
| `clock.py` | `FakeClock.now()` / `advance(duration)` |
| `outbound.py` | WhatsApp-like outbound message catcher |
| `whatsapp_transport.py` | Mock WhatsApp: inbound injector + outbound catcher + side-effect counters |
| `ingress_sim.py` | Allowlist → tools/outbound via mock transport (not Gateway) |
| `virtual_user.py` | Scripted Virtual User: inject audio/text, create reminders, assert state (E2E-01) |
| `inv_runner.py` | Discover/run `src/invariants/*` |
| `artifacts.py` | `report.json` / `report.md` writers |
| `adapters.py` | Stub calendar/commerce/self-mod/cron counters |
| `gateway_profile.py` | Harness JSON gateway profile + data paths |
| `gateway_harness.py` | Gateway double with `restart()` for E2E-10 prep |

Fail-closed proof: run CI with `--break-invariant` so `policy.ingress` allows everyone; `INV-INGRESS-001`/`002` must FAIL.

Gate E2E: `python3 scripts/run_e2e_01.py` or via `make test-ci` (e2e layer).
