# Scripts

| Script | Purpose |
| --- | --- |
| [`test-ci.sh`](./test-ci.sh) | **`test:ci`** entrypoint — unit + contract/INV-* + integration + gate e2e |
| [`run_test_ci.py`](./run_test_ci.py) | Layer runner (stdlib); writes `artifacts/test/ci/` + mirrors e2e-01 |
| [`run_e2e_01.py`](./run_e2e_01.py) | E2E-01 Virtual User voice reminder journey (also invoked by test:ci) |
| [`run_e2e_03.py`](./run_e2e_03.py) | E2E-03 Todo WhatsApp → Android journey (also invoked by test:ci) |
| [`backup-restore-placeholder.sh`](./backup-restore-placeholder.sh) | Documented backup/restore paths (no cloud in CI) |

```bash
./scripts/test-ci.sh                 # happy path — expect exit 0
./scripts/test-ci.sh --break-invariant   # fail-closed proof — expect exit ≠ 0
make test-ci
make test-ci-fail-closed             # proves broken INV is rejected
make e2e-01                          # E2E-01 alone
make e2e-03                          # E2E-03 alone
```

`PYTHONPATH` is set to `src/` so `harness`, `policy`, and `invariants` import cleanly.
