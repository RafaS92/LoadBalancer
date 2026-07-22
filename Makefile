.DEFAULT_GOAL := help

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BACKEND_DIR := $(ROOT_DIR)/backend
FRONTEND_DIR := $(ROOT_DIR)/frontend
NPM ?= npm

NAME ?= backend-a
HOST ?= 127.0.0.1
PORT ?= 9001
BACKEND_TEST_ARGS ?= -q

.PHONY: \
	help install backend-install frontend-install \
	backend frontend demo demo-a demo-b demo-c \
	test backend-test frontend-test \
	build frontend-build lint backend-lint \
	check backend-check frontend-check

help: ## Show the available project commands.
	@printf '%s\n' \
		'Project commands:' \
		'  make install                         Install backend and frontend dependencies' \
		'  make backend                         Run the load balancer' \
		'  make backend BACKEND_ARGS="..."      Pass options to the backend CLI' \
		'  make frontend                        Run the frontend development server' \
		'  make frontend FRONTEND_ARGS="..."    Pass options to Vite' \
		'  make demo NAME=api PORT=9010         Run one configurable demo backend' \
		'  make demo-a|demo-b|demo-c            Run a default demo backend instance' \
		'  make test                            Run backend and frontend tests' \
		'  make build                           Build the frontend production bundle' \
		'  make lint                            Run backend Ruff checks' \
		'  make check                           Lint, test, and build the complete project'

install: backend-install frontend-install ## Install all project dependencies.

backend-install: ## Install the backend and Python development tools.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" install

frontend-install: ## Install frontend dependencies.
	@cd "$(FRONTEND_DIR)" && "$(NPM)" install

backend: ## Run the load balancer; pass options with BACKEND_ARGS.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" run ARGS="$(BACKEND_ARGS)"

frontend: ## Run Vite; pass options with FRONTEND_ARGS.
	@cd "$(FRONTEND_DIR)" && "$(NPM)" run dev -- $(FRONTEND_ARGS)

demo: ## Run one configurable demo backend.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" demo \
		NAME="$(NAME)" HOST="$(HOST)" PORT="$(PORT)" ARGS="$(DEMO_ARGS)"

demo-a: ## Run backend-a on port 9001.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" demo-a

demo-b: ## Run backend-b on port 9002.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" demo-b

demo-c: ## Run backend-c on port 9003.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" demo-c

test: backend-test frontend-test ## Run every backend and frontend test.

backend-test: ## Run backend tests.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" test \
		PYTEST_ARGS="$(BACKEND_TEST_ARGS)"

frontend-test: ## Run frontend tests.
	@cd "$(FRONTEND_DIR)" && "$(NPM)" test -- $(FRONTEND_TEST_ARGS)

build: frontend-build ## Build production artifacts.

frontend-build: ## Type-check and build the frontend.
	@cd "$(FRONTEND_DIR)" && "$(NPM)" run build

lint: backend-lint ## Run project lint checks.

backend-lint: ## Run Ruff against the backend.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" lint

check: backend-check frontend-check ## Run every project verification command.

backend-check: ## Lint and test the backend.
	@$(MAKE) --no-print-directory -C "$(BACKEND_DIR)" check \
		PYTEST_ARGS="$(BACKEND_TEST_ARGS)"

frontend-check: frontend-test frontend-build ## Test and build the frontend.
