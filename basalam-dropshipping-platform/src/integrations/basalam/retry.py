import asyncio
from typing import Callable, Any, TypeVar

from .exceptions import TokenExpiredError, RateLimitError, BasalamAPIError

T = TypeVar("T")


class BasalamRetryPolicy:
    def __init__(self, client: "BasalamClient"):
        self.client = client
        self.delays = [1, 2, 4]

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
                    wait_time = (
                        e.retry_after
                        if e.retry_after
                        else self.delays[min(attempt, len(self.delays) - 1)]
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise
            except BasalamAPIError as e:
                if attempt < max_retries - 1 and e.code and 500 <= e.code < 600:
                    last_exception = e
                    await asyncio.sleep(self.delays[min(attempt, len(self.delays) - 1)])
                    continue
                raise

        raise last_exception
