from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return rate-limit errors in the standard error envelope."""
    return JSONResponse(
        status_code=429,
        content=_error_body("rate_limited", "Too many requests; please slow down."),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap FastAPI HTTPExceptions in the standard error envelope."""
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        body = detail
    else:
        body = _error_body("http_error", str(detail))
    return JSONResponse(status_code=exc.status_code, content=body)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    try:
        from opentelemetry import trace

        from gamebook_web.observability.tracing import span_set_error

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span_set_error(span, exc)
    except Exception:  # pragma: no cover
        pass
    logger.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url)
    return JSONResponse(
        status_code=500,
        content=_error_body("internal_error", "An internal server error occurred."),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the given FastAPI app."""
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
