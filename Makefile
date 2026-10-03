.PHONY: up down logs migrate test lint typecheck e2e
up:
	docker compose up --build
down:
	docker compose down
logs:
	docker compose logs -f
migrate:
	docker compose run --rm backend alembic upgrade head
test:
	docker compose run --rm backend pytest
	docker compose run --rm frontend pnpm test
lint:
	docker compose run --rm backend ruff check .
	docker compose run --rm frontend pnpm lint
typecheck:
	docker compose run --rm backend mypy app
	docker compose run --rm frontend pnpm typecheck
e2e:
	docker compose run --rm frontend pnpm e2e
