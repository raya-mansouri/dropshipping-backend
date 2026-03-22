## Context

The codebase currently reads configuration from 13 files using `os.getenv()`, `os.environ[]`, and unresolved `"{{placeholder}}"` strings. Problems:

- **No validation**: `int(os.getenv("IMAGE_MAX_WIDTH", "1920"))` — manual, error-prone type casting
- **No startup fail-fast**: `os.environ["DATABASE_URL"]` raises `KeyError` the first time a DB call is made, not at boot
- **Secrets in plaintext**: `SECRET_KEY = "{{SECRET_KEY}}"` — a literal placeholder that could be logged
- **Duplication**: `REDIS_URL` read independently in `deps.py`, `health.py`, and `celery_config.py`
- **`pydantic-settings ^2.1.0`** is already declared in `pyproject.toml` — zero new dependencies required

## Goals / Non-Goals

**Goals:**
- One `Settings(BaseSettings)` class in `src/core/config.py` as the only env read point
- Auto type-coercion and validation on startup (Pydantic handles `bool`, `int`, `float`)
- `SecretStr` for `secret_key`, `basalam_client_secret`, `minio_secret_key`
- `@lru_cache` so `.env` is parsed once per process
- CLAUDE.md rule banning `os.getenv` outside `config.py`

**Non-Goals:**
- Nested settings models (e.g. `settings.db.host`) — flat class is simpler and sufficient for current scale
- Multi-environment file switching (`.env.prod` / `.env.dev`) — environment-specific values are supplied via shell env vars in CI/CD, not file switching
- Secrets manager integration (Vault, AWS SSM) — out of scope; can be layered on top later

## Decisions

### Decision 1: Flat `Settings` class, not nested sub-models

**Options considered:**
- **Flat** (`settings.minio_endpoint`, `settings.minio_secret_key`, ...): simple, one file, no prefix routing
- **Nested** (`settings.minio.endpoint`, `settings.minio.secret_key`, ...): requires `env_nested_delimiter="__"` and `MINIO__ENDPOINT` in env

**Chosen: Flat.** The `.env.example` already uses `MINIO_ENDPOINT` (single underscore) and changing to double-underscore would break existing deployments. Flat is also easier to grep and debug.

---

### Decision 2: `@lru_cache` singleton, not module-level global

**Options considered:**
- **Module-level global** `settings = Settings()` at import time: simple, but untestable (can't override per test)
- **`@lru_cache` factory** `get_settings()`: returns the same instance after first call, but can be overridden in tests via `app.dependency_overrides`

**Chosen: `@lru_cache`.** FastAPI's dependency injection system integrates directly — tests override with `app.dependency_overrides[get_settings]`. Module-level globals cannot be overridden without monkey-patching.

---

### Decision 3: `SecretStr` for 3 fields only, not all strings

**Fields using `SecretStr`:** `secret_key`, `basalam_client_secret`, `minio_secret_key`

**Rationale:** `SecretStr` requires `.get_secret_value()` at every use site, which adds friction. Applying it to non-sensitive fields (e.g. `redis_url`, `kafka_bootstrap_servers`) would add boilerplate with no security benefit. Only credentials that must not appear in logs warrant the overhead.

---

### Decision 4: `database_url`, `secret_key`, `basalam_client_id`, `basalam_client_secret` are required (no default)

Fields with no default cause Pydantic to raise `ValidationError` at import time if unset. This is intentional: these values have no safe local fallback, and a misconfigured instance should not start silently.

`minio_secret_key` retains a default (`"minioadmin"`) because MinIO is optional infrastructure for local development.

---

### Decision 5: Remove `--env-file` from uvicorn command

The previous workaround was `uvicorn ... --env-file .env`. With `SettingsConfigDict(env_file=".env")`, the app loads `.env` itself. The `--env-file` flag is redundant and confusing — remove it from documentation and Makefile.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `basalam_client_id` and `basalam_client_secret` are required fields but may not be set in local dev | Add sensible dev placeholder in `.env.example`; document that these are only needed when testing Basalam OAuth |
| `lru_cache` caches the first call — if env changes after import, the cached value persists | This is desired behavior in production. For tests: call `get_settings.cache_clear()` in teardown if needed |
| `SecretStr.get_secret_value()` must be called explicitly — easy to forget | CLAUDE.md documents this pattern; runtime type errors will surface immediately in tests |

## Migration Plan

1. Create `src/core/config.py` with full `Settings` class
2. Update `src/core/database.py` first (most critical — currently broken with `{{DATABASE_URL}}`)
3. Update remaining 10 files in any order (all are independent)
4. Create `CLAUDE.md` with the env variable rule
5. Update `.env.example` with missing variables
6. Verify: `grep -rn "os\.getenv\|os\.environ" src/ --include="*.py"` returns zero results

**Rollback:** Each file change is independent. Revert `src/core/config.py` and restore `os.getenv` calls per-file if needed. No database migrations, no API changes, no external contracts affected.

## Open Questions

- None. All decisions above are unambiguous given the existing codebase constraints.
