"""HTTP request metrics middleware (T048/FR-030).

Counts every request by method/status. No PII: only the route template
(not the concrete path) and method/status.
"""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response


async def http_metrics_middleware(request: Request, call_next) -> Response:
    from gamebook_web.observability.tracing import get_metrics

    response = await call_next(request)
    try:
        route = request.scope.get("route")
        path_template = getattr(route, "path", request.url.path)
        get_metrics().http_requests_total.add(
            1,
            attributes={
                "method": request.method,
                "path": path_template,
                "status": str(response.status_code),
            },
        )
    except Exception:  # pragma: no cover — metrics must never break a request
        pass
    return response
