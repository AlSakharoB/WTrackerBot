FROM python:3.12-slim AS base

ENV PATH=/opt/venv/bin:$PATH \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

FROM base AS builder

WORKDIR /build

RUN python -m venv /opt/venv

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .


FROM builder AS test

COPY alembic.ini ./
COPY Dockerfile docker-compose.yml ./
COPY docker ./docker
COPY migrations ./migrations
COPY scripts ./scripts
COPY tests ./tests

RUN pip install --no-cache-dir ".[dev]"

CMD ["pytest", "-q", "-p", "no:cacheprovider"]


FROM base AS runtime

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app \
        --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && mkdir /backups \
    && chown app:app /backups

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY docker/entrypoint.sh /usr/local/bin/nutrition-bot-entrypoint

USER 10001:10001

ENTRYPOINT ["nutrition-bot-entrypoint"]
