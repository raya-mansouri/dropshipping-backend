import sys
from typing import Any, Dict, Optional

import structlog
from structlog.processors import JSONRenderer
from structlog.stdlib import ProcessorFormatter

import logging
import logging.config

import sentry_sdk
from sentry_sdk.integrations.logging import SentryHandler

from src.core.config import get_settings


def _add_timestamp(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    from datetime import datetime, timezone

    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def configure_logging() -> None:
    settings = get_settings()
    log_level = settings.log_level.upper()
    sentry_dsn = settings.sentry_dsn
    app_env = settings.app_env

    is_production = app_env == "production"

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_timestamp,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if is_production:
        processors.append(JSONRenderer(serializer=_format_json))
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(format_my_extra=True, colors=True)
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    log_level_int = getattr(logging, log_level, logging.INFO)

    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=app_env,
            integrations=[SentryHandler(level=log_level_int)],
            send_default_pii=False,
            traces_sample_rate=0.1 if not is_production else 0.01,
        )

    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "formatter": {
                "()": ProcessorFormatter,
                "processor": JSONRenderer()
                if is_production
                else structlog.dev.ConsoleRenderer(),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "formatter",
                "stream": sys.stdout,
            },
        },
        "root": {"level": log_level, "handlers": ["console"]},
        "loggers": {
            "uvicorn": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_config)

    logger = structlog.get_logger()
    logger.info(
        "logging_configured",
        log_level=log_level,
        app_env=app_env,
        sentry_enabled=bool(sentry_dsn),
    )


def _format_json(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
