import asyncio
import functools
import structlog
import random
from typing import Callable, Any, Tuple, Type, TypeVar

from .exceptions import TokenExpiredError, RateLimitError, BasalamAPIError

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class BasalamRetryPolicy:
    def __init__(self, client: "BasalamClient"):
        self.client = client
        self.delays = [1, 2, 4]
        self.jitter_factor = 0.3

    def _calculate_delay(self, attempt: int, base_delay: float) -> float:
        """
        Calculate delay with jitter to prevent thundering herd.

        Adds random jitter within +/- jitter_factor of the base delay.
        """
        jitter = base_delay * self.jitter_factor * 2
        return max(0, base_delay + random.uniform(-jitter, jitter))

    async def execute(
        self, func: Callable[..., Any], max_retries: int = 3, *args, **kwargs
    ) -> Any:
        last_exception = None

        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except TokenExpiredError as e:
                last_exception = e
                if attempt < max_retries - 1:
                    await self.client.refresh_access_token()
                    continue
                raise
            except RateLimitError as e:
                last_exception = e
                if attempt < max_retries - 1:
                    base_delay = (
                        e.retry_after
                        if e.retry_after
                        else self.delays[min(attempt, len(self.delays) - 1)]
                    )
                    delay = self._calculate_delay(attempt, float(base_delay))
                    await asyncio.sleep(delay)
                    continue
                raise
            except BasalamAPIError as e:
                if attempt < max_retries - 1 and e.code and 500 <= e.code < 600:
                    last_exception = e
                    base_delay = self.delays[min(attempt, len(self.delays) - 1)]
                    delay = self._calculate_delay(attempt, float(base_delay))
                    await asyncio.sleep(delay)
                    continue
                raise

        raise last_exception


def retry_on_error(
    max_attempts: int = 3,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    base_delay: float = 1.0,
    jitter_factor: float = 0.3,
):
    """Decorator that retries async functions with exponential backoff and jitter.

    Args:
        max_attempts: Maximum number of attempts before giving up.
        retryable_exceptions: Tuple of exception types that should trigger a retry.
        base_delay: Base delay in seconds for exponential backoff.
        jitter_factor: Fraction of delay to add as random jitter (±30%).

    Returns:
        A decorator that wraps an async function with retry logic.

    Usage::

        @retry_on_error(max_attempts=5, retryable_exceptions=(ConnectionError,))
        async def fetch_data():
            ...
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 0:
                        from src.core.metrics import retry_success_total

                        retry_success_total.labels(
                            exception_type=type(last_exception).__name__
                        ).inc()
                    return result
                except retryable_exceptions as e:
                    last_exception = e
                    from src.core.metrics import retry_attempts_total

                    retry_attempts_total.labels(
                        exception_type=type(e).__name__,
                        attempt=str(attempt + 1),
                    ).inc()
                    if attempt >= max_attempts - 1:
                        from src.core.metrics import retry_exhausted_total

                        retry_exhausted_total.labels(
                            exception_type=type(e).__name__
                        ).inc()
                        raise
                    delay = base_delay * (2**attempt)
                    jitter = delay * jitter_factor * random.uniform(-1, 1)
                    await asyncio.sleep(max(0, delay + jitter))
            raise last_exception

        return wrapper

    return decorator
