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
    description="Orbita — Financial Intelligence Platform for the Angolan Capital Market (BODIVA).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow deployed frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Routers base (portados do Kimi) ===
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

# === Novos routers de investimento ===
app.include_router(investor_router)
app.include_router(goals_router)
app.include_router(strategies_router)
app.include_router(ai_router)
app.include_router(academy_router)
app.include_router(scenarios_router)
app.include_router(signals_router)
app.include_router(international_router)
app.include_router(tax_router)


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
