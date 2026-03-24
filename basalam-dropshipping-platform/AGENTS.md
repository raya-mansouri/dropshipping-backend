# AGENTS.md — Agent Instructions for Basalam Dropshipping Platform

## Dev Environment

```bash
# Install
poetry install

# Run server
make dev                    # uvicorn on :8000 with --reload

# Test
poetry run pytest                          # all tests
poetry run pytest tests/unit/ -v           # unit only
poetry run pytest tests/integration/ -v   # integration only
poetry run pytest -k "test_name" -v        # single test

# Lint after edits
make lint                   # ruff check
make format                 # black + isort (run before committing)

# Database
make migrate                           # apply pending migrations
make migrate-create message="desc"     # generate new migration after model change
```

## Architecture Rules for Agents

1. **Domain structure is mandatory**: new features go in `src/domains/<name>/` with
   `models.py`, `schemas.py`, `repository/`, `service/` — never skip layers.

2. **Always use Unit of Work**: DB writes must go through `UnitOfWork` from
   `src/core/repository/unit_of_work.py`, never raw `session.commit()`.

3. **Never name a column `metadata`**: SQLAlchemy's `DeclarativeBase` reserves this.
   Use `extra_data = Column("metadata", JSONB)` to preserve the DB column name.

4. **Webhook idempotency is required**: all webhook handlers must use
   `src/integrations/webhooks/idempotency.py` to deduplicate before processing.

5. **New shop platform**: implement `ShopConnector` port from `src/integrations/shop/ports.py`,
   place in `src/integrations/shop/connectors/`, register in `src/integrations/shop/registry.py`.

6. **New notification channel**: implement adapter from `src/integrations/notification/ports.py`,
   place in `src/integrations/notification/adapters/`.

## Testing Requirements

- Unit tests must not touch the database — mock repositories.
- Integration tests use async SQLite (aiosqlite); see `tests/conftest.py` for fixtures.
- E2E tests run full order flows; use the `httpx` test client from conftest.
- After modifying any model, run `make migrate-create` to generate migration.
- After lint changes (ruff), always re-run `make format` before committing.

## PR Instructions

- Title format: `[DOMAIN] short description` — e.g., `[inventory] fix reservation race condition`
- Commit format: conventional commits — `feat:`, `fix:`, `refactor:`, `test:`, `chore:`
- All PRs must pass `make lint` and `make test` before merge.
- Target branch: `master`
