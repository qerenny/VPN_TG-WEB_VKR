FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.7.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONPATH=/app/telegram_bot/src:/app/shared/src

RUN apt-get update && \
    apt-get install -y build-essential libpq-dev curl procps && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app

# Copy only requirements to cache them in docker layer
COPY ./telegram_bot/pyproject.toml ./telegram_bot/poetry.lock ./telegram_bot/
COPY ./shared/pyproject.toml ./shared/

# Create a fake shared package structure to satisfy the path dependency during install
RUN mkdir -p shared/src/shared && touch shared/src/shared/__init__.py

# Install dependencies (no root)
WORKDIR /app/telegram_bot
RUN poetry install --no-root

# Copy source code
COPY ./shared /app/shared
COPY ./telegram_bot/src /app/telegram_bot/src

# Install root package and shared package
RUN poetry install --no-interaction

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD pgrep -f "telebot" || exit 1

CMD ["python", "-m", "telegram_bot.main"]
