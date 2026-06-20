"""
Orbita API — FastAPI main application entry point.
Wires all routers, middleware, and event handlers.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    description="Orbita — Financial Intelligence Platform for the Angolan Capital Market (BODIVA).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the deployed frontend + Cloudflare tunnel origins
# The JWT token is sent via Authorization header (not cookies),
# so allow_credentials can be False, which works with wildcard origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False for wildcard origins to work
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
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


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "app": settings.app_name, "version": "1.0.0"}


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "description": "Orbita Financial Intelligence API",
    }
