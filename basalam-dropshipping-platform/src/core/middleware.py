"""
HTTP Middleware
==============
Request-scoped middleware for logging, tracing, and observability.

Uses pure ASGI middleware instead of BaseHTTPMiddleware to avoid
thread pool execution that breaks async event loop.
"""
import uuid

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send, Message


class CorrelationIdMiddleware:
    """
    Pure ASGI middleware that binds a request_id to structlog context vars.

    - Accepts an existing ID from the ``X-Request-ID`` header.
    - Generates a UUID4 when the header is absent.
    - Adds the ID to the response headers so callers can correlate.
    - Cleans up context vars after each request to avoid leaking state.

    Unlike BaseHTTPMiddleware, this runs entirely in the async event loop
    without thread pool overhead.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract request ID from headers
        headers = dict(scope.get("headers", []))
        request_id = None
        for key, value in headers.items():
            if key == b"x-request-id":
                request_id = value.decode("utf-8", errors="replace")
                break
        if not request_id:
            request_id = str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Inject X-Request-ID into response headers
        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.clear_contextvars()
