# Pydantic Settings — Best Practices Research

## Sources
- [FastAPI Settings Guide](https://fastapi.tiangolo.com/advanced/settings/)
- [Pydantic Settings Concepts](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Pydantic Settings API Reference](https://docs.pydantic.dev/latest/api/pydantic_settings/)
- [Centralizing FastAPI Config — David Muraya](https://davidmuraya.com/blog/centralizing-fastapi-configuration-with-pydantic-settings-and-env-files/)
- [Manage Env Vars with Pydantic — Towards Data Science](https://towardsdatascience.com/manage-environment-variables-with-pydantic/)

---

## Key Best Practices Found

| Practice | How | Rationale |
|---|---|---|
| Single `Settings` class | `src/core/config.py`, one `BaseSettings` subclass | Single source of truth; avoids scattered reads |
| Load `.env` automatically | `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")` | No need for `python-dotenv` calls |
| Cache the instance | `@lru_cache` on `get_settings()` | `.env` parsed exactly once per process |
| Inject into routes | `Depends(get_settings)` | Testable; easy to override in tests |
| Group with `env_prefix` | `SettingsConfigDict(env_prefix="MINIO_")` | Clean namespacing for related vars |
| Protect secrets | `SecretStr` type | Values redacted in `repr()` and logs |
| Nested models | `env_nested_delimiter="__"` | `DB__HOST` → `settings.db.host` |
| Multi-environment | `.env.dev`, `.env.prod`, loaded by name | No code changes between environments |
| Required fields | No default value | App crashes at **startup** (not runtime) if missing |
| Case insensitivity | Default behavior | Field `secret_key` matches `SECRET_KEY` env var |

---

## Pattern: Settings Class

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Required (no default → startup crash if missing)
    database_url: str
    secret_key: SecretStr

    # Optional (sensible defaults)
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    minio_use_ssl: bool = False          # auto-parsed from "true"/"false"
    image_max_width: int = 1920          # auto-coerced from string


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

## Pattern: Injection via Depends

```python
from typing import Annotated
from fastapi import Depends

@app.get("/info")
async def info(settings: Annotated[Settings, Depends(get_settings)]):
    return {"env": settings.app_env}
```

## Pattern: SecretStr Unwrapping

```python
# Only unwrap where the raw value is strictly needed
raw = settings.secret_key.get_secret_value()
token = jwt.encode(payload, raw, algorithm=settings.jwt_algorithm)
```

---

## Anti-Patterns Found in This Codebase

| Anti-pattern | File | Problem |
|---|---|---|
| `os.getenv("REDIS_URL", ...)` repeated | deps.py, health.py, celery_config.py | Duplicated, no validation |
| `os.environ["DATABASE_URL"]` | core/database.py | KeyError raised at **first use**, not startup |
| `SECRET_KEY = "{{SECRET_KEY}}"` | api/v1/auth.py | Literal placeholder in production code |
| `int(os.getenv("IMAGE_MAX_WIDTH", "1920"))` | image_service.py | Manual type coercion Pydantic handles |
| `os.getenv("MINIO_USE_SSL", "false").lower() == "true"` | image_service.py | Manual bool parsing |
| `"{{BASALAM_CLIENT_ID}}"` | shop/adapters/basalam.py | Unresolved template placeholder |

---

## Files Affected (13 files with env var reads)

```
src/core/database.py           → DATABASE_URL
src/core/logging.py            → LOG_LEVEL, SENTRY_DSN, APP_ENV
src/main.py                    → CORS_ORIGINS
src/api/deps.py                → SECRET_KEY, REDIS_URL
src/api/v1/auth.py             → SECRET_KEY (hardcoded {{}}), ALGORITHM, expiry consts
src/api/v1/health.py           → REDIS_URL, KAFKA_BOOTSTRAP_SERVERS
src/workers/celery_config.py   → REDIS_URL
src/workers/consumers/init_topics.py → KAFKA_BOOTSTRAP_SERVERS
src/integrations/basalam/image_service.py → 11× MINIO_*, IMAGE_*, CDN_BASE_URL
src/integrations/shop/adapters/basalam.py → BASALAM_CLIENT_ID, BASALAM_CLIENT_SECRET, BASE_URL
```
