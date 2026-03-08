.PHONY: sync-env dev up down test-isolated
# Edge contract targets
EDGE_REPO ?= ../../edge_proxy
EDGE_BASE_COMPOSE ?= docker-compose.yml

sync-env:
	python scripts/sync_runtime_env.py

dev:
	$(MAKE) sync-env
	bash $(EDGE_REPO)/scripts/dev_edge_up.sh
	docker compose --env-file .env -f $(EDGE_BASE_COMPOSE) -f compose.edge.yml up -d
	@echo "http://context-api.localhost"

up:
	$(MAKE) sync-env
	docker compose --env-file .env -f $(EDGE_BASE_COMPOSE) up -d

down:
	docker compose --env-file .env -f $(EDGE_BASE_COMPOSE) -f compose.edge.yml down

test-isolated:
	python scripts/run_pytest_isolated.py $(PYTEST_ARGS)
