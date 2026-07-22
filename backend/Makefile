.DEFAULT_GOAL := help

BACKEND_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT_DIR := $(abspath $(BACKEND_DIR)/..)
VENV ?= $(ROOT_DIR)/.venv
PYTHON ?= python3

PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
LOAD_BALANCER := $(VENV)/bin/load-balancer
DEMO_BACKEND := $(VENV)/bin/demo-backend

NAME ?= backend-a
HOST ?= 127.0.0.1
PORT ?= 9001
PYTEST_ARGS ?= -q

.PHONY: help venv install run demo demo-a demo-b demo-c test lint check

help: ## Show the available backend commands.
	@printf '%s\n' \
		'Backend commands:' \
		'  make install                 Create the venv and install backend + dev tools' \
		'  make run                     Run the load balancer with default settings' \
		'  make run ARGS="..."          Pass options to the load-balancer CLI' \
		'  make demo                    Run one configurable demo backend' \
		'  make demo NAME=api PORT=9010 Configure the demo backend' \
		'  make demo-a|demo-b|demo-c    Run a default demo backend instance' \
		'  make test                    Run all backend tests' \
		'  make test PYTEST_ARGS="..."  Pass options or a path to pytest' \
		'  make lint                    Run Ruff checks' \
		'  make check                   Run lint and tests'

venv: ## Create the root virtual environment when it does not exist.
	@test -x "$(PIP)" || "$(PYTHON)" -m venv "$(VENV)"

install: venv ## Install the backend and development dependencies.
	@"$(PIP)" install --editable "$(ROOT_DIR)[dev]"

run: ## Run the load balancer; pass CLI options with ARGS.
	@test -x "$(LOAD_BALANCER)" || { printf '%s\n' 'Run make install first.'; exit 1; }
	@"$(LOAD_BALANCER)" $(ARGS)

demo: ## Run one demo backend; customize NAME, HOST, PORT, or ARGS.
	@test -x "$(DEMO_BACKEND)" || { printf '%s\n' 'Run make install first.'; exit 1; }
	@"$(DEMO_BACKEND)" --name "$(NAME)" --host "$(HOST)" --port "$(PORT)" $(ARGS)

demo-a: ## Run backend-a on port 9001.
	@$(MAKE) --no-print-directory demo NAME=backend-a PORT=9001

demo-b: ## Run backend-b on port 9002.
	@$(MAKE) --no-print-directory demo NAME=backend-b PORT=9002

demo-c: ## Run backend-c on port 9003.
	@$(MAKE) --no-print-directory demo NAME=backend-c PORT=9003

test: ## Run backend tests; customize arguments with PYTEST_ARGS.
	@test -x "$(PYTEST)" || { printf '%s\n' 'Run make install first.'; exit 1; }
	@cd "$(ROOT_DIR)" && "$(PYTEST)" $(PYTEST_ARGS)

lint: ## Run Ruff against the backend project.
	@test -x "$(RUFF)" || { printf '%s\n' 'Run make install first.'; exit 1; }
	@cd "$(ROOT_DIR)" && "$(RUFF)" check backend

check: lint test ## Run every backend verification command.
