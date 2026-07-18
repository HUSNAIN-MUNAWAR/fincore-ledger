.PHONY: install api-test api-lint api-type web-install web-lint web-type web-build migrate seed run-api verify compose-up compose-down

install:
	python -m pip install -r apps/api/requirements-dev.txt

api-test:
	cd apps/api && pytest -q

api-lint:
	cd apps/api && ruff check .

api-type:
	cd apps/api && mypy fincore

web-install:
	cd apps/web && npm ci

web-lint:
	cd apps/web && npm run lint

web-type:
	cd apps/web && npm run typecheck

web-build:
	cd apps/web && rm -rf .next tsconfig.tsbuildinfo && NEXT_TELEMETRY_DISABLED=1 npm run build

migrate:
	cd apps/api && alembic upgrade head

seed:
	cd apps/api && python -m fincore.seed

run-api:
	cd apps/api && uvicorn fincore.main:app --reload --host 0.0.0.0 --port 8000

verify: api-lint api-type api-test web-lint web-type web-build

compose-up:
	docker compose up --build

compose-down:
	docker compose down -v
