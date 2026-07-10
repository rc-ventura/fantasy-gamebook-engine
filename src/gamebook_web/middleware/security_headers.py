"""Security headers middleware (FR-060).

Sets ``X-Frame-Options``, ``X-Content-Type-Options``, and ``Referrer-Policy``
on every response, including errors.
"""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


async def security_headers_middleware(request: Request, call_next) -> Response:
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response
