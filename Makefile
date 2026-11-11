# Unix helper targets. On Windows use install.ps1 / plaq.py instead.
PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python

.PHONY: help install install-lite install-dev doctor init test serve lint clean

help:
	@echo "Plaq-OS"
	@echo "  make install       full install into .venv"
	@echo "  make install-lite  skip Stim/PyMatching"
	@echo "  make doctor        environment diagnostics"
	@echo "  make test          pytest"
	@echo "  make serve         workbench on :8000"
	@echo "  make lint          ruff"

install:
	$(PYTHON) scripts/install.py --dev

install-lite:
	$(PYTHON) scripts/install.py --lite --dev

install-dev: install

doctor:
	$(PY) plaq.py doctor

init:
	$(PY) plaq.py init

test:
	$(PY) -m pytest -q

serve:
	$(PY) plaq.py serve --port 8000

lint:
	$(PY) -m ruff check --config ruff.toml apps services packages engines

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
