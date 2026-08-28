.PHONY: setup pipeline dashboard

VENV := .venv
PYTHON := $(VENV)/bin/python

setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv $(VENV); \
		uv pip install --python $(PYTHON) -r requirements.txt; \
	else \
		python3 -m venv $(VENV); \
		$(PYTHON) -m pip install --upgrade pip; \
		$(PYTHON) -m pip install -r requirements.txt; \
	fi

pipeline:
	$(PYTHON) load_data.py
	$(PYTHON) analysis.py

dashboard:
	$(PYTHON) -m streamlit run dashboard.py --server.headless true
