# Scripts

| Script | Purpose |
| --- | --- |
| [`test-ci.sh`](./test-ci.sh) | **`test:ci`** entrypoint — unit + contract/INV-* + integration |
| [`run_test_ci.py`](./run_test_ci.py) | Layer runner (stdlib); writes `artifacts/test/ci/` |

```bash
./scripts/test-ci.sh                 # happy path — expect exit 0
./scripts/test-ci.sh --break-invariant   # fail-closed proof — expect exit ≠ 0
make test-ci
make test-ci-fail-closed             # proves broken INV is rejected
```

`PYTHONPATH` is set to `src/` so `harness`, `policy`, and `invariants` import cleanly.
