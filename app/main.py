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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


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
    allow_origins=["*"],
    allow_credentials=False,
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
    """Enhanced health check — verifies DB + AI + SerpAPI key presence."""
    status = {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
        "checks": {
            "database": "unchecked",
            "ai_key": "missing",
            "serpapi_key": "missing",
        },
    }

    # Check database connectivity
    try:
        from app.database import engine
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        status["checks"]["database"] = "ok"
    except Exception as e:
        status["checks"]["database"] = f"error: {str(e)[:100]}"

    # Check API keys
    if settings.anthropic_api_key:
        status["checks"]["ai_key"] = "configured"
    if hasattr(settings, "serpapi_key") and settings.serpapi_key:
        status["checks"]["serpapi_key"] = "configured"

    overall = all(
        v == "ok" or v == "configured"
        for v in status["checks"].values()
    )
    if not overall:
        status["status"] = "degraded"

    return status


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
