from typing import Annotated

import redis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from fincore.core.config import get_settings
from fincore.core.middleware import REQUEST_COUNT, REQUEST_DURATION_SUM
from fincore.db.session import get_db

router = APIRouter(tags=["Health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
def ready(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    redis_status = "unavailable"
    try:
        client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.25)
        redis_status = "ready" if client.ping() else "unavailable"
    except Exception:
        if get_settings().env not in {"development", "test"}:
            raise
    return {"status": "ready", "database": "ready", "redis": redis_status}


@router.get("/metrics")
def metrics() -> Response:
    lines = ["# HELP fincore_http_requests_total HTTP requests", "# TYPE fincore_http_requests_total counter"]
    for (path, status), count in sorted(REQUEST_COUNT.items()):
        lines.append(f'fincore_http_requests_total{{path="{path}",status="{status}"}} {count}')
    lines.extend(
        [
            "# HELP fincore_http_request_duration_seconds_sum HTTP duration sum",
            "# TYPE fincore_http_request_duration_seconds_sum counter",
        ]
    )
    for path, duration in sorted(REQUEST_DURATION_SUM.items()):
        lines.append(f'fincore_http_request_duration_seconds_sum{{path="{path}"}} {duration}')
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
