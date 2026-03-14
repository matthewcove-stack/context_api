.PHONY: sync-env dev up down test-isolated
# Edge contract targets
EDGE_REPO ?= ../../edge_proxy
EDGE_BASE_COMPOSE ?= docker-compose.yml
EDGE_OVERLAY_COMPOSE ?= compose.edge.yml
COMPOSE_WITH_EDGE = docker compose --env-file .env -f $(EDGE_BASE_COMPOSE) -f $(EDGE_OVERLAY_COMPOSE)

sync-env:
	python scripts/sync_runtime_env.py

dev:
	$(MAKE) sync-env
	bash $(EDGE_REPO)/scripts/dev_edge_up.sh
	$(COMPOSE_WITH_EDGE) up -d
	@echo "http://context-api.localhost"

up:
	$(MAKE) sync-env
	$(COMPOSE_WITH_EDGE) up -d
	@echo "http://context-api.localhost"

down:
	$(COMPOSE_WITH_EDGE) down

test-isolated:
	python scripts/run_pytest_isolated.py $(PYTEST_ARGS)
