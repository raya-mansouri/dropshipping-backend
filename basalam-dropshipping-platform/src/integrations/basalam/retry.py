import asyncio
import random
from typing import Callable, Any, TypeVar

from .exceptions import TokenExpiredError, RateLimitError, BasalamAPIError

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
