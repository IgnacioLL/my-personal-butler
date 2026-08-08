# Harness (T0)

| Module | Role |
| --- | --- |
| `clock.py` | `FakeClock.now()` / `advance(duration)` |
| `outbound.py` | WhatsApp-like outbound message catcher |
| `ingress_sim.py` | Allowlist → tools/outbound stub (not Gateway) |
| `inv_runner.py` | Discover/run `src/invariants/*` |
| `artifacts.py` | `report.json` / `report.md` writers |

Fail-closed proof: run CI with `--break-invariant` so `policy.ingress` allows everyone; `INV-INGRESS-001`/`002` must FAIL.
