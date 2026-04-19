# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM docker.basalam.dev/basalam/uvicorn-gunicorn:python3.10 AS builder

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.1.1

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.in-project true \
    && poetry install --no-interaction --no-ansi --only main

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM docker.basalam.dev/basalam/uvicorn-gunicorn:python3.10

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appgroup \
    && useradd -r -g appgroup -s /bin/sh appuser

COPY --from=builder /app/.venv .venv
COPY --from=builder /app/pyproject.toml ./
COPY src/ src/
COPY scripts/ scripts/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
