## ADDED Requirements

### Requirement: All datetime columns SHALL use timezone-aware types
Every SQLAlchemy `Column(DateTime)` in the codebase SHALL use `DateTime(timezone=True)`, producing `TIMESTAMPTZ` columns in PostgreSQL. No bare `DateTime` columns SHALL exist in any model.

#### Scenario: New model uses DateTime with timezone
- **WHEN** a developer creates a new SQLAlchemy model with a datetime column
- **THEN** the column MUST be defined as `Column(DateTime(timezone=True))`
- **AND** the generated migration produces `TIMESTAMPTZ` in PostgreSQL

#### Scenario: Existing bare DateTime columns are migrated
- **WHEN** the migration runs
- **THEN** all existing `TIMESTAMP WITHOUT TIME ZONE` columns are altered to `TIMESTAMP WITH TIME ZONE`
- **AND** existing UTC values are preserved without modification

### Requirement: All Python datetimes SHALL be timezone-aware UTC
All datetime values created in application code SHALL be timezone-aware UTC. The system SHALL use `datetime.now(timezone.utc)` exclusively for current-time generation. Naive datetimes SHALL NOT be created or stored.

#### Scenario: Code generates a current timestamp
- **WHEN** application code needs the current time
- **THEN** it MUST use `datetime.now(timezone.utc)`
- **AND** the result includes `tzinfo=timezone.utc`

#### Scenario: Code converts a Unix timestamp to datetime
- **WHEN** application code converts a Unix timestamp to a datetime
- **THEN** it MUST use `datetime.fromtimestamp(ts, tz=timezone.utc)`
- **AND** SHALL NOT use `datetime.utcfromtimestamp()` (deprecated)

### Requirement: No timezone stripping
Application code SHALL NOT strip timezone information from datetime objects. The pattern `.replace(tzinfo=None)` SHALL NOT be used on datetime objects.

#### Scenario: Comparing a database-loaded datetime with a generated datetime
- **WHEN** code compares a datetime loaded from the database with `datetime.now(timezone.utc)`
- **THEN** both values SHALL be timezone-aware
- **AND** the comparison MUST succeed without `TypeError`

### Requirement: Alembic migration for timezone column conversion
A single Alembic migration SHALL convert all existing `TIMESTAMP` columns to `TIMESTAMPTZ`. The migration SHALL NOT modify existing data values, as they are already UTC.

#### Scenario: Migration runs on existing database
- **WHEN** `alembic upgrade head` is executed
- **THEN** all datetime columns are `TIMESTAMPTZ`
- **AND** existing timestamp values are unchanged
- **AND** asyncpg returns timezone-aware datetimes for all datetime columns
