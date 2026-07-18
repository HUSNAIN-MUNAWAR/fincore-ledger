from __future__ import annotations

import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from fincore.core.config import get_settings

logger = structlog.get_logger()
REQUEST_COUNT: defaultdict[tuple[str, int], int] = defaultdict(int)
REQUEST_DURATION_SUM: defaultdict[str, float] = defaultdict(float)
RATE_BUCKETS: defaultdict[tuple[str, int], int] = defaultdict(int)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_bytes:
            return Response(status_code=413, content="Request body too large")
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
        correlation_id = request.headers.get("x-correlation-id") or f"cor_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        REQUEST_COUNT[(request.url.path, response.status_code)] += 1
        REQUEST_DURATION_SUM[request.url.path] += elapsed
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        await logger.ainfo(
            "request.completed",
            request_id=request_id,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(("/health/", "/metrics")):
            return await call_next(request)
        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"
        minute = int(time.time() // 60)
        key = (client_ip, minute)
        RATE_BUCKETS[key] += 1
        if RATE_BUCKETS[key] > settings.rate_limit_per_minute:
            return Response(
                status_code=429,
                media_type="application/json",
                content='{"error":{"code":"RATE_LIMITED","message":"Too many requests."}}',
                headers={"Retry-After": "60"},
            )
        if len(RATE_BUCKETS) > 10_000:
            stale = [bucket for bucket in RATE_BUCKETS if bucket[1] < minute - 1]
            for bucket in stale:
                RATE_BUCKETS.pop(bucket, None)
        return await call_next(request)
