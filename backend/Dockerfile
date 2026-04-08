FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.7.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONPATH=/app/backend/src:/app/shared/src:/app/telegram_bot/src

RUN apt-get update && \
    apt-get install -y build-essential libpq-dev curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app

# Copy only requirements to cache them in docker layer
COPY ./backend/pyproject.toml ./backend/poetry.lock ./backend/
COPY ./shared/pyproject.toml ./shared/
COPY ./telegram_bot/pyproject.toml ./telegram_bot/

# Create fake local package structures to satisfy path dependencies during install
RUN mkdir -p shared/src/shared telegram_bot/src/telegram_bot && \
    touch shared/src/shared/__init__.py telegram_bot/src/telegram_bot/__init__.py

# Install dependencies (no root)
WORKDIR /app/backend
RUN poetry install --no-root

# Copy source code
COPY ./shared /app/shared
COPY ./telegram_bot /app/telegram_bot
COPY ./backend/src /app/backend/src

# Install root package and shared package
RUN poetry install --no-interaction

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
