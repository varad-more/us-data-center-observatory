# Backend image serving both the API and the CLI worker.
#
# Two stages: a builder that compiles wheels, and a slim runtime that carries no
# build toolchain. The runtime runs as a non-root user because it fetches and
# parses untrusted bytes from public websites.

FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install .

# ------------------------------------------------------------------ runtime --

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 helios

COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv/helios

COPY alembic.ini ./
COPY database ./database
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker

RUN mkdir -p /var/lib/helios/evidence && chown -R helios:helios /var/lib/helios /srv/helios

USER helios

EXPOSE 8000

CMD ["uvicorn", "helios_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
