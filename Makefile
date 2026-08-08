.PHONY: test test-ci test-ci-fail-closed e2e-01 e2e-02 e2e-03 e2e-04 e2e-05 e2e-06 e2e-07 e2e-08 e2e-09 help

help:
	@echo "Targets:"
	@echo "  test-ci              Run CI pipeline (unit + INV contract + integration + gate e2e)"
	@echo "  test-ci-fail-closed  Prove fail-closed: broken INV must exit non-zero"
	@echo "  e2e-01               Run E2E-01 Virtual User voice reminder journey"
	@echo "  e2e-02               Run E2E-02 Habit escalation ladder journey (T4)"
	@echo "  e2e-03               Run E2E-03 Todo WhatsApp → Android journey"
	@echo "  e2e-04               Run E2E-04 Calendar soft confirm journey"
	@echo "  e2e-05               Run E2E-05 Diet plan → groceries journey"
	@echo "  e2e-06               Run E2E-06 Booksy propose → approve → book (T5)"
	@echo "  e2e-07               Run E2E-07 Shopping with cap / freeze (+ deny; T6)"
	@echo "  e2e-08               Run E2E-08 Self-mod patch accept + deny (T7)"
	@echo "  e2e-09               Run E2E-09 Ignored hard approval expiry"
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

e2e-02:
	@PYTHONPATH=src python3 ./scripts/run_e2e_02.py

e2e-03:
	@PYTHONPATH=src python3 ./scripts/run_e2e_03.py

e2e-04:
	@PYTHONPATH=src python3 ./scripts/run_e2e_04.py

e2e-05:
	@PYTHONPATH=src python3 ./scripts/run_e2e_05.py

e2e-06:
	@PYTHONPATH=src python3 ./scripts/run_e2e_06.py

e2e-07:
	@PYTHONPATH=src python3 ./scripts/run_e2e_07.py

e2e-08:
	@PYTHONPATH=src python3 ./scripts/run_e2e_08.py

e2e-09:
	@PYTHONPATH=src python3 ./scripts/run_e2e_09.py

test: test-ci
