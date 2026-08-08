.PHONY: test test-ci test-ci-fail-closed help

help:
	@echo "Targets:"
	@echo "  test-ci              Run CI pipeline (unit + INV contract + integration)"
	@echo "  test-ci-fail-closed  Prove fail-closed: broken INV must exit non-zero"
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

test: test-ci
