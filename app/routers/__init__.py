"""
Orbita API routers.
"""
from app.routers.auth import router as auth_router
from app.routers.bank_accounts import router as bank_accounts_router
from app.routers.budget import router as budget_router
from app.routers.conciliation import router as conciliation_router
from app.routers.statements import router as statements_router
from app.routers.transactions import router as transactions_router
from app.routers.news import router as news_router
from app.routers.portfolio import router as portfolio_router
from app.routers.broker_files import router as broker_files_router
from app.routers.market_data import router as market_data_router
from app.routers.watchlist import router as watchlist_router

# Novos routers de investimento (Sprint 3)
from app.routers.investment import (
    investor_router,
    goals_router,
    scenarios_router,
    signals_router,
    international_router,
    tax_router,
    strategies_router,
)

__all__ = [
    "auth_router",
    "bank_accounts_router",
    "budget_router",
    "conciliation_router",
    "statements_router",
    "transactions_router",
    "news_router",
    "portfolio_router",
    "broker_files_router",
    "market_data_router",
    "watchlist_router",
    "investor_router",
    "goals_router",
    "scenarios_router",
    "signals_router",
    "international_router",
    "tax_router",
    "strategies_router",
]
