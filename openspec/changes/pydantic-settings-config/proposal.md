## Why

Environment variables are read through scattered `os.getenv()`, `os.environ[]`, and unresolved `"{{placeholder}}"` strings across 13 files — with no type validation, no startup failure on missing vars, and secrets exposed as plain strings. Centralizing to `pydantic-settings` eliminates all of these issues with zero new dependencies (already in `pyproject.toml`).

## What Changes

- **CREATE** `src/core/config.py` — single `Settings(BaseSettings)` class covering all 20+ environment variables with type coercion, validation, and `SecretStr` for sensitive fields
- **REMOVE** all `os.getenv`, `os.environ`, and `"{{placeholder}}"` reads from 11 files
- **CREATE** `CLAUDE.md` — project rule: "always use `get_settings()`, never `os.getenv`"
- **UPDATE** `.env.example` — add missing variables (`BASE_URL`, `APP_ENV`, `CORS_ORIGINS`, `JWT_ALGORITHM`)

## Capabilities

### New Capabilities
- `pydantic-settings-config`: Centralized, validated, cached configuration via `BaseSettings` with `SecretStr` protection for credentials, auto `.env` loading, and `@lru_cache` singleton

### Modified Capabilities
- (none — internal implementation change only; no API contracts or database schemas change)

## Impact

- **All 11 files** importing `os` for config will drop that import and use `from src.core.config import get_settings`
- `SecretStr` fields (`secret_key`, `basalam_client_secret`, `minio_secret_key`) require `.get_secret_value()` at call sites — prevents accidental logging
- App now **fails at startup** (not at first use) if required vars like `DATABASE_URL` or `SECRET_KEY` are missing
- `MINIO_USE_SSL`, `IMAGE_MAX_WIDTH`, `IMAGE_MAX_HEIGHT`, `IMAGE_QUALITY`, `IMAGE_HTTP_TIMEOUT` are now auto-coerced by Pydantic — no manual `int(os.getenv(...))` or `.lower() == "true"` casts
- No new dependencies — `pydantic-settings ^2.1.0` already declared in `pyproject.toml`
- Tests: `get_settings()` can be overridden via `app.dependency_overrides[get_settings] = lambda: Settings(...)` for easy test isolation
