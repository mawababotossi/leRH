from __future__ import annotations

import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

CORRELATION_ID_CTX_VAR: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = CORRELATION_ID_CTX_VAR.set(correlation_id)

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            CORRELATION_ID_CTX_VAR.reset(token)


def get_correlation_id() -> str | None:
    return CORRELATION_ID_CTX_VAR.get()
