.PHONY: install clean build test test-all

install:
	@command -v pipx >/dev/null 2>&1 || (echo "pipx not found; please install pipx or run 'make build'"; exit 1)
	@echo "Installing editable package into pipx-managed env 'bills-agent' (dev extras)"
	@pipx runpip bills-agent pip install -e '.[dev]' 2>/dev/null || pipx install -e . --force --pip-args "--index-url https://pypi.org/simple" 2>/dev/null || (echo "pipx install failed; try 'make build' instead"; exit 1)
	@echo "Done."

clean:
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

build: clean
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip
	. .venv/bin/activate && pip install -e '.[dev]'
	. .venv/bin/activate && pytest

test:
	@if [ ! -d ".venv" ]; then \
		echo "Virtual environment not found. Creating it..."; \
		python3 -m venv .venv; \
		. .venv/bin/activate && pip install --upgrade pip && pip install -e '.[dev]'; \
	fi
	@. .venv/bin/activate && PYTHONPATH=. pytest tests/unit

test-all:
	@if [ ! -d ".venv" ]; then \
		echo "Virtual environment not found. Creating it..."; \
		python3 -m venv .venv; \
		. .venv/bin/activate && pip install --upgrade pip && pip install -e '.[dev]'; \
	fi
	@. .venv/bin/activate && PYTHONPATH=. pytest tests/
