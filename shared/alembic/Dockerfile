FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.7.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONPATH=/app/shared/src:/app

RUN apt-get update && \
    apt-get install -y build-essential libpq-dev curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app

# Copy only requirements to cache them in docker layer
COPY ./shared/pyproject.toml ./shared/

# Create a fake shared package structure to satisfy the path dependency during install
RUN mkdir -p shared/src/shared && touch shared/src/shared/__init__.py

# Install dependencies (no root)
WORKDIR /app/shared
RUN poetry install --no-root

# Copy source code and config
WORKDIR /app
COPY ./shared ./shared
COPY ./shared/alembic ./alembic
COPY ./shared/alembic.ini ./alembic.ini

# Install project
WORKDIR /app/shared
RUN poetry install --no-interaction

# Ensure alembic is in path (it should be by default with global install)
ENV PATH="/usr/local/bin:$PATH"

CMD ["sh", "-c", "cd /app && alembic upgrade head"]
