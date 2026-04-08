
alembic-revision:
	cd shared && poetry run alembic revision --autogenerate -m "Migration"

alembic-upgrade:
	cd shared && poetry run alembic upgrade head

backend:
	poetry run --directory backend uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

install-backend:
	cd backend && poetry install

frontend:
	cd frontend && __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=localhost npm run dev -- --host 0.0.0.0 --port 5173

build-frontend:
	cd frontend && npm run build

deploy-frontend-prod:
	docker compose -f docker-compose.prod.yml --profile tools run --rm frontend

install-frontend:
	cd frontend && npm install

bot:
	poetry run --directory telegram_bot python -m telegram_bot.main

install-bot:
	cd telegram_bot && poetry install

install-shared:
	cd shared && poetry install

dev:
	poetry run --directory backend uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 & \
	cd frontend && npm run dev

lint:
	poetry run --directory backend ruff check backend/src

check_format:
	poetry run --directory backend black --check backend/src

format:
	poetry run --directory backend black backend/src

format_ruff:
	poetry run --directory backend ruff format backend/src

all: lint check_format

.PHONY: backend frontend build-frontend deploy-frontend-prod dev bot install-backend install-bot install-shared install-frontend \
        lint check_format format format_ruff all
