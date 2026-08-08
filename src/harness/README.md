# Harness (T0+)

| Module | Role |
| --- | --- |
| `clock.py` | `FakeClock.now()` / `advance(duration)` |
| `outbound.py` | WhatsApp-like outbound message catcher |
| `whatsapp_transport.py` | Mock WhatsApp: inbound injector + outbound catcher + side-effect counters |
| `ingress_sim.py` | Allowlist → tools/outbound via mock transport (not Gateway) |
| `inv_runner.py` | Discover/run `src/invariants/*` |
| `artifacts.py` | `report.json` / `report.md` writers |
| `adapters.py` | Stub calendar/commerce/self-mod/cron counters |

Fail-closed proof: run CI with `--break-invariant` so `policy.ingress` allows everyone; `INV-INGRESS-001`/`002` must FAIL.
