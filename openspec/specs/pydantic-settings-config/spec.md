## ADDED Requirements

### Requirement: Single settings class as source of truth
The system SHALL expose all runtime configuration through a single `Settings` class in `src/core/config.py`. No other file SHALL read environment variables directly via `os.getenv`, `os.environ`, or hardcoded placeholder strings.

#### Scenario: Application reads database URL at startup
- **WHEN** the application starts
- **THEN** `DATABASE_URL` is read once from the environment via `Settings.database_url` and used throughout the app's lifetime

#### Scenario: Forbidden pattern detected
- **WHEN** code contains `os.getenv(` or `os.environ[` or `"{{` outside of `src/core/config.py`
- **THEN** a CLAUDE.md rule flags it as a violation to be corrected

---

### Requirement: All variables validated and type-coerced at startup
The system SHALL validate and coerce all environment variable values to their declared Python types when the application starts. Pydantic SHALL raise a `ValidationError` listing all invalid or missing fields before the app serves any requests.

#### Scenario: Missing required variable
- **WHEN** `DATABASE_URL` is not set in the environment or `.env` file
- **THEN** the application raises a `ValidationError` at import time, before binding to any port

#### Scenario: Boolean variable from string
- **WHEN** `MINIO_USE_SSL=true` is set in the environment
- **THEN** `settings.minio_use_ssl` resolves to Python `True` (not the string `"true"`)

#### Scenario: Integer variable from string
- **WHEN** `IMAGE_MAX_WIDTH=800` is set in the environment
- **THEN** `settings.image_max_width` resolves to Python `int(800)`, not `"800"`

#### Scenario: Float variable from string
- **WHEN** `IMAGE_HTTP_TIMEOUT=10.5` is set in the environment
- **THEN** `settings.image_http_timeout` resolves to Python `float(10.5)`

---

### Requirement: Secrets protected with SecretStr
The system SHALL declare sensitive fields (`secret_key`, `basalam_client_secret`, `minio_secret_key`) as `pydantic.SecretStr`. These values SHALL NOT appear in plaintext in logs, stack traces, or `repr()` output.

#### Scenario: Secret field in logs
- **WHEN** a `Settings` instance is logged or printed
- **THEN** secret fields appear as `SecretStr('**********')`, not their actual value

#### Scenario: Consuming a secret value
- **WHEN** code needs the raw value (e.g. signing a JWT)
- **THEN** it calls `.get_secret_value()` at that exact call site, not at module level

---

### Requirement: Settings instance cached with lru_cache
The system SHALL create the `Settings` instance exactly once per process using `@lru_cache`. The `.env` file SHALL NOT be re-parsed on every request or function call.

#### Scenario: Repeated calls return the same instance
- **WHEN** `get_settings()` is called multiple times during request handling
- **THEN** the same `Settings` object is returned without re-reading the environment

#### Scenario: Test override
- **WHEN** a test uses `app.dependency_overrides[get_settings] = lambda: Settings(database_url="sqlite+aiosqlite:///./test.db", ...)`
- **THEN** the overridden settings are used for that test in isolation

---

### Requirement: .env file loaded automatically
The system SHALL load variables from a `.env` file in the project root automatically via `SettingsConfigDict(env_file=".env")`. No call to `load_dotenv()` or `python-dotenv` SHALL be required.

#### Scenario: Variable present in .env but not in shell environment
- **WHEN** `LOG_LEVEL=DEBUG` is in `.env` and not exported in the shell
- **THEN** `settings.log_level` resolves to `"DEBUG"`

#### Scenario: Shell environment overrides .env
- **WHEN** `LOG_LEVEL=WARNING` is exported in the shell AND `LOG_LEVEL=DEBUG` is in `.env`
- **THEN** `settings.log_level` resolves to `"WARNING"` (shell takes precedence)

---

### Requirement: .env.example kept as complete reference
The project SHALL maintain a `.env.example` file that lists every variable consumed by `Settings`, with safe placeholder values. It SHALL be kept in sync whenever a new field is added to `Settings`.

#### Scenario: New field added to Settings
- **WHEN** a developer adds a new field to `Settings` in `src/core/config.py`
- **THEN** a corresponding entry MUST be added to `.env.example` before the change is merged

#### Scenario: Developer onboarding
- **WHEN** a new developer clones the repository
- **THEN** running `cp .env.example .env` provides a functional template for local setup

---

### Requirement: CLAUDE.md rule enforces the pattern
The project SHALL have a `CLAUDE.md` rule in `basalam-dropshipping-platform/CLAUDE.md` that explicitly forbids direct `os` env reads and defines the required `get_settings()` pattern with examples.

#### Scenario: AI assistant adds new configuration
- **WHEN** an AI coding assistant adds a new configurable value
- **THEN** the CLAUDE.md rule guides it to add the field to `Settings` and read via `get_settings()`
