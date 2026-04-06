"""
HTTP Middleware
==============
Request-scoped middleware for logging, tracing, and observability.
"""
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Binds a request_id to structlog context vars for every HTTP request.

    - Accepts an existing ID from the ``X-Request-ID`` header.
    - Generates a UUID4 when the header is absent.
    - Adds the ID to the response headers so callers can correlate.
    - Cleans up context vars after each request to avoid leaking state.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        structlog.contextvars.clear_contextvars()
        return response
