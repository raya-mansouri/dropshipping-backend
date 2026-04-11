## Why

The codebase has an inconsistent timezone strategy: `TimestampMixin` uses `DateTime(timezone=True)` (Postgres `TIMESTAMPTZ`), but 20+ columns across domain models use bare `DateTime` (Postgres `TIMESTAMP` without timezone). All models insert `datetime.now(timezone.utc)` (timezone-aware), but the non-TZ columns strip that info on storage. This mismatch causes `TypeError` when comparing DB-loaded naive datetimes with aware ones, breaks cross-server consistency, and will silently corrupt timestamps if the database session timezone ever changes.

## What Changes

- Change all `Column(DateTime)` to `Column(DateTime(timezone=True))` across all domain models, aligning with the `TimestampMixin` pattern already in `database.py`
- Replace `datetime.utcfromtimestamp()` (deprecated since Python 3.12) with `datetime.fromtimestamp(ts, tz=timezone.utc)`
- Remove `timestamp.replace(tzinfo=None)` calls that strip timezone awareness
- Add Alembic migration to alter affected columns from `TIMESTAMP` to `TIMESTAMPTZ`
- Verify all datetime comparisons work consistently (aware vs aware)

## Capabilities

### New Capabilities

- `timezone-consistency`: Enforces timezone-aware UTC datetimes across all models, columns, and runtime code

### Modified Capabilities

- `basalam-webhooks`: Webhook processors strip timezone info via `replace(tzinfo=None)` — must use aware comparisons throughout

## Impact

- **Database**: Alembic migration altering ~20+ columns from `TIMESTAMP` to `TIMESTAMPTZ`. Data is already UTC so no value conversion needed.
- **Models**: All domain models in `src/domains/*/models.py` with `Column(DateTime)` — webhooks, shops, inventory, notifications, system_logs
- **Workers**: Celery tasks and Kafka consumers that construct datetime values
- **Integrations**: Webhook processors in `src/integrations/webhooks/processors/base.py` with deprecated `utcfromtimestamp` and tz-stripping
- **API**: Response schemas will now serialize datetimes with `+00:00` offset — potential **BREAKING** change for clients that parse ISO strings naively
