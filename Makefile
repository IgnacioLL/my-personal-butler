.PHONY: test test-ci help

help:
	@echo "Targets:"
	@echo "  test-ci   Run the CI test pipeline (stub until TASK-01)"
	@echo "  test      Alias for test-ci"

test-ci:
	@./scripts/test-ci.sh

test: test-ci
