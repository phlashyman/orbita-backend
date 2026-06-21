"""
Orbita API — FastAPI main application entry point.
Wires all routers, middleware, and event handlers.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine, Base
from app.routers import (
    auth_router,
    bank_accounts_router,
    budget_router,
    transactions_router,
    statements_router,
    conciliation_router,
    news_router,
    portfolio_router,
    broker_files_router,
    market_data_router,
    watchlist_router,
    # Novos routers de investimento
    investor_router,
    goals_router,
    strategies_router,
    scenarios_router,
    signals_router,
    international_router,
    tax_router,
    ai_router,
    academy_router,
)


import logging

logger = logging.getLogger("orbita")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: try to create tables on startup, resilient to missing DB."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created successfully.")
    except Exception as e:
        logger.warning(f"Could not connect to database on startup: {e}")
        logger.warning("The API will start, but DB-dependent endpoints will return 503.")
        logger.warning("Check DATABASE_URL env var and ensure PostgreSQL is running.")
    yield
    try:
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title=settings.app_name,
    description="Orbita - Financial Intelligence Platform for the Angolan Capital Market (BODIVA).",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(",") if settings.cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ---------------------------------------------------------------------------
# Sentry error tracking (optional)
# ---------------------------------------------------------------------------
try:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        environment=settings.railway_environment or "development",
    )
except (ImportError, AttributeError):
    pass  # Sentry not configured or not installed

# ---------------------------------------------------------------------------
# Rate limiting (via slowapi)
# ---------------------------------------------------------------------------
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    limiter = None  # slowapi not installed

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(bank_accounts_router)
app.include_router(budget_router)
app.include_router(transactions_router)
app.include_router(statements_router)
app.include_router(conciliation_router)
app.include_router(news_router)
app.include_router(portfolio_router)
app.include_router(broker_files_router)
app.include_router(market_data_router)
app.include_router(watchlist_router)

# Novos routers de investimento
app.include_router(investor_router)
app.include_router(goals_router)
app.include_router(strategies_router)
app.include_router(ai_router)
app.include_router(academy_router)
app.include_router(scenarios_router)
app.include_router(signals_router)
app.include_router(international_router)
app.include_router(tax_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    """Fast health check for Railway post-deploy — always returns 200."""
    return {"status": "ok", "app": settings.app_name, "version": "1.0.0"}


@app.get("/health/full", tags=["Health"])
async def health_check_full():
    """Full health check — verifies DB + AI + SerpAPI key presence."""
    status = {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
        "checks": {"database": "unchecked", "ai_key": "missing", "serpapi_key": "missing"},
    }
    try:
        from app.database import engine
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        status["checks"]["database"] = "ok"
    except Exception as e:
        status["checks"]["database"] = f"error: {str(e)[:100]}"
        status["status"] = "degraded"
    if settings.anthropic_api_key:
        status["checks"]["ai_key"] = "configured"
    if settings.serpapi_key:
        status["checks"]["serpapi_key"] = "configured"
    return status


@app.get("/health/db", tags=["Health"])
async def health_check_db():
    """Database-only health check. Returns full connection detail for debugging."""
    import os
    raw = os.environ.get("DATABASE_URL", "NOT SET")
    # Mask password
    masked = raw
    if "@" in masked:
        parts = masked.split("@")
        host_part = parts[1] if len(parts) > 1 else ""
        user_part = parts[0].split("://")[1] if "://" in parts[0] else "???"
        if ":" in user_part:
            user_part = user_part.split(":")[0] + ":****"
        masked = parts[0].split("://")[0] + "://" + user_part + "@" + host_part

    try:
        from app.database import engine
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql("SELECT 1")
            row = result.scalar()
        if row == 1:
            return {
                "database": "CONNECTED",
                "url_masked": masked,
                "tables_created": "auto (lifespan)",
                "using": settings.database_url.split("://")[0] if "://" in settings.database_url else "unknown",
            }
    except Exception as e:
        return {
            "database": "ERROR",
            "url_masked": masked,
            "using": settings.database_url.split("://")[0] if "://" in settings.database_url else "unknown",
            "error": str(e)[:200],
        }


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "description": "Orbita Financial Intelligence API",
        "disclaimer": "Esta plataforma nao constitui aconselhamento financeiro. "
                       "Os dados apresentados sao para fins informativos. "
                       "Consulte um profissional certificado antes de tomar decisoes de investimento.",
    }
