## 1. Create Central Settings Module

- [x] 1.1 Create `src/core/config.py` with `Settings(BaseSettings)` class covering all variables: `database_url`, `redis_url`, `kafka_bootstrap_servers`, `secret_key` (SecretStr), `jwt_algorithm`, `access_token_expire_minutes`, `refresh_token_expire_days`, `basalam_client_id`, `basalam_client_secret` (SecretStr), `base_url`, `minio_endpoint`, `minio_access_key`, `minio_secret_key` (SecretStr), `minio_bucket`, `minio_region`, `minio_use_ssl` (bool), `cdn_base_url`, `image_max_width` (int), `image_max_height` (int), `image_quality` (int), `image_format`, `image_http_timeout` (float), `app_env`, `log_level`, `sentry_dsn`, `cors_origins`
- [x] 1.2 Add `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)` to `Settings`
- [x] 1.3 Add `@lru_cache` decorated `get_settings() -> Settings` factory function below the class

## 2. Replace Env Reads in Core Layer

- [x] 2.1 Update `src/core/database.py`: remove `import os`, replace `DATABASE_URL = os.environ["DATABASE_URL"]` with `from src.core.config import get_settings` and `DATABASE_URL = get_settings().database_url`
- [x] 2.2 Update `src/core/logging.py`: remove `import os`, replace 3× `os.getenv` for `LOG_LEVEL`, `SENTRY_DSN`, `APP_ENV` with `settings = get_settings()` and `settings.log_level`, `settings.sentry_dsn`, `settings.app_env`

## 3. Replace Env Reads in API Layer

- [x] 3.1 Update `src/api/deps.py`: remove `import os`, replace `os.getenv("SECRET_KEY", "{{SECRET_KEY}}")` with `get_settings().secret_key.get_secret_value()`, replace `os.getenv("REDIS_URL", ...)` with `get_settings().redis_url`
- [x] 3.2 Update `src/api/v1/auth.py`: remove `import os` (if present), replace `SECRET_KEY = "{{SECRET_KEY}}"` with `get_settings().secret_key.get_secret_value()`, replace hardcoded `ALGORITHM = "HS256"` with `get_settings().jwt_algorithm`, replace `ACCESS_TOKEN_EXPIRE_MINUTES = 30` and `REFRESH_TOKEN_EXPIRE_DAYS = 7` with values from settings
- [x] 3.3 Update `src/api/v1/health.py`: remove `import os`, replace all 3× `os.getenv` for `REDIS_URL` and `KAFKA_BOOTSTRAP_SERVERS` with `get_settings().redis_url` and `get_settings().kafka_bootstrap_servers`

## 4. Replace Env Reads in Workers Layer

- [x] 4.1 Update `src/workers/celery_config.py`: remove `import os`, replace `REDIS_URL = os.getenv("REDIS_URL", ...)` with `from src.core.config import get_settings` and `REDIS_URL = get_settings().redis_url`
- [x] 4.2 Update `src/workers/consumers/init_topics.py`: remove `import os`, replace `KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", ...)` with `get_settings().kafka_bootstrap_servers`

## 5. Replace Env Reads in Integrations Layer

- [x] 5.1 Update `src/integrations/basalam/image_service.py`: remove `import os`, replace all 11× `os.getenv` calls in `__init__` with `_s = get_settings()` and read `_s.minio_endpoint`, `_s.minio_access_key`, `_s.minio_secret_key.get_secret_value()`, `_s.minio_bucket`, `_s.minio_region`, `_s.minio_use_ssl`, `_s.cdn_base_url`, `_s.image_max_width`, `_s.image_max_height`, `_s.image_quality`, `_s.image_format`, `_s.image_http_timeout`
- [x] 5.2 Update `src/integrations/shop/adapters/basalam.py`: replace `"{{BASALAM_CLIENT_ID}}"` with `get_settings().basalam_client_id`, `"{{BASALAM_CLIENT_SECRET}}"` with `get_settings().basalam_client_secret.get_secret_value()`, `"{{BASE_URL}}/integrations/basalam/callback"` with `f"{get_settings().base_url}/integrations/basalam/callback"`

## 6. Update App Entry Point

- [x] 6.1 Update `src/main.py`: replace `os.getenv("CORS_ORIGINS", "*").split(",")` with `get_settings().cors_origins.split(",")`

## 7. Add Project Rule and Update Env Example

- [x] 7.1 Create `basalam-dropshipping-platform/CLAUDE.md` with the env variable rule: forbid `os.getenv`/`os.environ` outside `src/core/config.py`, document required `get_settings()` pattern with code example, document `SecretStr.get_secret_value()` usage, document steps to add a new variable
- [x] 7.2 Update `.env.example`: add missing variables `BASE_URL`, `APP_ENV`, `CORS_ORIGINS`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS` with placeholder values

## 8. Verify

- [x] 8.1 Run `grep -rn "os\.getenv\|os\.environ" src/ --include="*.py"` — expect zero results outside `src/core/config.py`
- [x] 8.2 Run `grep -rn '"{{' src/ --include="*.py"` — expect zero results (only `{{` in notification template strings which use double-brace for substitution, not env placeholders)
- [x] 8.3 Start the app: `poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000` (no `--env-file` flag needed) — expect clean startup with no `ValidationError`
