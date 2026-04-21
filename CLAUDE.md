# Basalam Dropshipping Platform

## Tech Stack
- **Backend**: FastAPI + Python 3.11
- **Database**: PostgreSQL via SQLAlchemy 2.0 async + asyncpg
- **Migrations**: Alembic
- **Queue**: Celery + Redis
- **Messaging**: Kafka (aiokafka)
- **Validation**: Pydantic v2
- **Auth**: JWT (python-jose)
- **Monitoring**: Prometheus + Sentry
- **Container**: Docker Compose

## Architecture

### Domain-Driven Design (DDD)
Each domain under `src/domains/<domain>/` has a strict 4-layer structure:
```
models.py          # SQLAlchemy ORM models (DeclarativeBase)
schemas.py         # Pydantic v2 request/response schemas
repository/        # DB access — extend BaseRepository from core
  base.py (or named files per aggregate)
service/           # Business logic — depends on repos, never on HTTP
```

**Active domains**: `accounts`, `audit_logs`, `fraud_detection`, `integration_logs`,
`inventory`, `notifications`, `orders`, `payments`, `pricing`, `products`,
`product_validation`, `shops`, `system_logs`, `webhooks`

### Core Infrastructure (`src/core/`)
- `database.py` — async SQLAlchemy session factory
- `config.py` — pydantic-settings Config
- `repository/base.py` — `BaseRepository[Model]` with QueryBuilder, soft-delete, audit trail
- `repository/unit_of_work.py` — Unit of Work pattern (always use UoW to group repo ops)
- `events/` — Domain event base + typed events per domain (order, inventory, product, payment, pricing)
- `events/publisher.py` — Event publisher

### API Layer (`src/api/v1/`)
- Routers: `auth`, `health`, `orders`, `products`, `shops`
- `src/api/deps.py` — FastAPI dependency injection (db session, current user, etc.)

### Integrations (`src/integrations/`)
Uses **Ports & Adapters** (hexagonal) pattern:
- `shop/ports.py` → interfaces → `shop/connectors/` (Basalam, Shopify, WooCommerce)
- `notification/ports.py` → interfaces → `notification/adapters/` (sms, in_app, webhook)
- `basalam/` — Basalam-specific client, rate limiter, retry, product sync, image service
- `webhooks/` — Idempotency, retry, processors per event type (inventory, order, payment, product)

### Workers (`src/workers/`)
- `celery_config.py` — Celery + Redis broker setup
- `tasks/` — Celery async tasks (inventory_tasks, etc.)
- `consumers/` — Kafka consumers (inventory, order, product)

## Key Patterns

### Adding a new domain
1. Create `src/domains/<name>/models.py` — SQLAlchemy model inheriting from `Base`
2. Create `src/domains/<name>/schemas.py` — Pydantic v2 schemas
3. Create `src/domains/<name>/repository/<name>.py` — extends `BaseRepository`
4. Create `src/domains/<name>/service/<name>_service.py` — business logic
5. Add Alembic migration: `make migrate-create message="add <name>"`
6. Register router in `src/main.py`

### Repository usage (always use UoW)
```python
async with UnitOfWork(session) as uow:
    repo = OrderRepository(uow.session)
    order = await repo.create({...})
    await uow.commit()
```

### Webhook idempotency
All webhook processors use `src/integrations/webhooks/idempotency.py`.
Events must be deduplicated before processing.

### Column naming pitfall
Do NOT name a SQLAlchemy column `metadata` — it shadows `Base.metadata`.
Use `extra_data = Column("metadata", JSONB)` instead.

## Dev Commands
```bash
make install          # Install deps via poetry
make dev              # Run uvicorn with reload on :8000
make test             # Run all tests with pytest
make lint             # Ruff check
make format           # Black + isort
make migrate          # alembic upgrade head
make migrate-create message="desc"  # Create new migration
make docker-up        # Start all services
make docker-down      # Stop services
```

## Testing
```
tests/
├── conftest.py            # Shared fixtures (async DB session, test client)
├── unit/                  # Pure unit tests — no DB
├── integration/           # Test with real DB (idempotency, webhooks)
└── e2e/                   # Full order flow tests
```
Run a single test: `poetry run pytest tests/unit/test_inventory_reservation.py -v`

## Environment
See `.env.example` for all required env vars.
Key vars: `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `KAFKA_BOOTSTRAP_SERVERS`,
`SECRET_KEY`, `SENTRY_DSN`, `BASALAM_API_KEY`
