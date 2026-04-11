## Context

The platform uses FastAPI + SQLAlchemy 2.0 async with asyncpg against PostgreSQL. The base `TimestampMixin` in `src/core/database.py` correctly uses `DateTime(timezone=True)` + `datetime.now(timezone.utc)`, producing `TIMESTAMPTZ` columns. However, 20+ columns across domain models (webhooks, shops, inventory, notifications, system_logs) use bare `Column(DateTime)` — creating `TIMESTAMP WITHOUT TIME ZONE` columns.

All code inserts timezone-aware UTC datetimes (`datetime.now(timezone.utc)`), but the bare `DateTime` columns strip the timezone info at the database boundary. Additionally, `src/integrations/webhooks/processors/base.py` explicitly strips timezone awareness with `.replace(tzinfo=None)` and uses the deprecated `datetime.utcfromtimestamp()`.

## Goals / Non-Goals

**Goals:**
- All datetime columns use `TIMESTAMPTZ` in PostgreSQL
- All Python datetimes are timezone-aware UTC — no naive datetimes anywhere
- Eliminate deprecated `datetime.utcnow()` and `datetime.utcfromtimestamp()` usage
- Alembic migration that safely converts existing data

**Non-Goals:**
- Localizing datetimes for display (that's a presentation-layer concern)
- Changing the Celery timezone config (already set to UTC)
- Adding new datetime columns or tables
- Changing API response schemas beyond the timezone offset appearing in ISO strings

## Decisions

### 1. Use `DateTime(timezone=True)` on all columns

**Decision**: Change every `Column(DateTime)` to `Column(DateTime(timezone=True))`.

**Rationale**: This is what `TimestampMixin` already does. It produces `TIMESTAMPTZ` in Postgres, which stores values as UTC and returns timezone-aware datetimes via asyncpg. Alternatives:
- *Add `server_default=func.now()`*: Doesn't help with application-generated timestamps, and our code generates all timestamps in Python.
- *Use bare `DateTime` +约定约定 convention "always UTC"*: Fragile. No enforcement. Already proven to drift.

### 2. Replace deprecated APIs

**Decision**:
- `datetime.utcfromtimestamp(ts)` → `datetime.fromtimestamp(ts, tz=timezone.utc)`
- `timestamp.replace(tzinfo=None)` → remove the `.replace()` call, keep timezone awareness

**Rationale**: `utcfromtimestamp` returns naive datetime and is deprecated since Python 3.12. The `.replace(tzinfo=None)` was a workaround for comparing naive DB values with aware values — once everything is aware, this workaround is unnecessary.

### 3. Migration strategy: `ALTER COLUMN ... TYPE TIMESTAMPTZ`

**Decision**: Single Alembic migration that alters all affected columns. No data conversion needed since all existing values are already UTC.

**Rationale**: `TIMESTAMP` to `TIMESTAMPTZ` is a safe cast in PostgreSQL when the session timezone is UTC (which it should be). The values don't change — only the column type metadata does. This requires no downtime for small-to-medium tables.

**Alternative considered**: Blue-green migration with new columns + backfill. Overkill for this — the data is already correct, only the type annotation changes.

### 4. Accept the breaking ISO format change

**Decision**: Accept that API responses will now include `+00:00` in ISO datetime strings.

**Rationale**: This is technically a breaking change for clients that parse ISO strings with a fixed format (e.g., `strftime` without offset). However:
- All well-formed ISO 8601 parsers handle `+00:00`
- The alternative (stripping timezone before serialization) defeats the purpose
- Clients should use proper datetime parsing, not string matching

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **Breaking API change**: `+00:00` appears in datetime strings | Announce in changelog. Standard ISO 8601 parsers handle this. |
| **Migration locks tables during ALTER COLUMN** | Run during low-traffic window. For large tables, use `SET lock_timeout` and batch. |
| **asyncpg returns `datetime` with tzinfo after migration** | This is the desired behavior. Test that all comparisons still work. |
| **Third-party libraries expect naive datetimes** | Audit integrations. Most modern Python libs handle aware datetimes. |

## Open Questions

- None — the fix is mechanical and well-scoped.
