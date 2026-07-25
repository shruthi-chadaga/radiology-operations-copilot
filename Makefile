.PHONY: install format lint typecheck test test-integration build compose-validate up down logs seed seed-pacs

install:
	cd backend && env -u PYTHONPATH uv sync --group dev
	cd frontend && npx --yes pnpm@10.14.0 install

format:
	cd backend && env -u PYTHONPATH uv run ruff format app tests alembic
	cd frontend && npx --yes pnpm@10.14.0 exec prettier --write .

lint:
	cd backend && env -u PYTHONPATH uv run ruff check app tests alembic
	cd frontend && npx --yes pnpm@10.14.0 lint

typecheck:
	cd backend && env -u PYTHONPATH uv run mypy app
	cd frontend && npx --yes pnpm@10.14.0 typecheck

test:
	cd backend && env -u PYTHONPATH uv run pytest -q
	cd frontend && npx --yes pnpm@10.14.0 test

test-integration:
	docker compose up -d --build postgres redis orthanc-source orthanc-destination backend
	docker compose exec -T backend python -m app.pacs.seed_dicom
	docker compose exec -T backend python -m app.pacs.connected_smoke

build:
	cd frontend && npx --yes pnpm@10.14.0 build

compose-validate:
	docker compose config --quiet

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

seed:
	docker compose exec backend python -m app.db.seed

seed-pacs:
	docker compose exec backend python -m app.pacs.seed_dicom
