from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fincore.api import admin, auth, health, operations, transactions, wallets
from fincore.core.config import get_settings
from fincore.core.errors import DomainError
from fincore.core.logging import configure_logging
from fincore.core.middleware import RateLimitMiddleware, RequestContextMiddleware

configure_logging()
settings = get_settings()
app = FastAPI(
    title="FinCore Ledger API",
    version="1.0.0",
    description=(
        "Ledger-first, multi-tenant wallet and payment processing reference platform. "
        "Not a licensed or certified real-money payment institution."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key", "X-Request-ID", "X-Correlation-ID"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(ValueError)
async def validation_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "DOMAIN_VALIDATION_ERROR",
                "message": str(exc),
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(wallets.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(operations.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
