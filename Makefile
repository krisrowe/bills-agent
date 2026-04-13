.PHONY: setup test test-all test-claude clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e '.[dev]'

test:
	.venv/bin/pytest

test-all:
	.venv/bin/pytest tests/

test-claude:
	@echo "Running Claude Code integration tests."
	@echo "Requires: claude on PATH, ANTHROPIC_API_KEY set."
	@echo "Each test makes a real API call to Anthropic."
	@echo "Uses a stub Monarch MCP server — no real financial data accessed."
	@echo ""
	.venv/bin/pytest tests/claude/ -v

clean:
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
