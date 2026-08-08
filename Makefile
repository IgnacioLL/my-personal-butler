.PHONY: test test-ci test-ci-fail-closed e2e-01 e2e-03 e2e-04 help

help:
	@echo "Targets:"
	@echo "  test-ci              Run CI pipeline (unit + INV contract + integration + gate e2e)"
	@echo "  test-ci-fail-closed  Prove fail-closed: broken INV must exit non-zero"
	@echo "  e2e-01               Run E2E-01 Virtual User voice reminder journey"
	@echo "  e2e-03               Run E2E-03 Todo WhatsApp → Android journey"
	@echo "  e2e-04               Run E2E-04 Calendar soft confirm journey"
	@echo "  test                 Alias for test-ci"

test-ci:
	@./scripts/test-ci.sh

# Expects failure. Exits 0 only when the broken-invariant run fails as required.
test-ci-fail-closed:
	@echo "==> proving fail-closed (broken INV must not pass)"
	@if ./scripts/test-ci.sh --break-invariant; then \
		echo "ERROR: broken invariant mode exited 0 — fail-closed proof FAILED"; \
		exit 1; \
	else \
		echo "==> fail-closed proof PASS (CI correctly rejected broken INV)"; \
		exit 0; \
	fi

e2e-01:
	@PYTHONPATH=src python3 ./scripts/run_e2e_01.py

e2e-03:
	@PYTHONPATH=src python3 ./scripts/run_e2e_03.py

e2e-04:
	@PYTHONPATH=src python3 ./scripts/run_e2e_04.py

test: test-ci
