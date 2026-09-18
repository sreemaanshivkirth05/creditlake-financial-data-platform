.PHONY: install run serve test lint verify quality demo benchmark

PYTHON ?= python

install:
	$(PYTHON) -m pip install -c requirements.lock.txt -e '.[dev]'

run:
	$(PYTHON) -m creditlake.cli run --as-of 2026-09-17

serve:
	$(PYTHON) -m creditlake.cli serve

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

verify:
	$(PYTHON) scripts/verify_pipeline.py --output docs/evidence/recovery-validation.json

quality:
	$(PYTHON) -m creditlake.cli quality

demo:
	$(PYTHON) scripts/export_demo.py

benchmark:
	$(PYTHON) scripts/benchmark.py --rows 100000
