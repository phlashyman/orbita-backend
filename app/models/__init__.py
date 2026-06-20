"""Import all models so Alembic can discover them."""
from app.models.family import Family
from app.models.user import User
from app.models.bank_account import BankAccount
from app.models.budget_category import BudgetCategory
from app.models.transaction import TransactionManual
from app.models.bank_statement import BankStatement
from app.models.conciliation import ConciliationLog
from app.models.market_news import MarketNews
from app.models.broker import Broker
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.portfolio_holding import PortfolioHolding
from app.models.trade import Trade
from app.models.broker_file_upload import BrokerFileUpload
from app.models.watchlist import WatchlistItem
from app.models.bodiva_market import (
    MarketSnapshot, OrderBookSnapshot, BondMaster, ImportLog,
    YieldCurveHistory, IncomeEvent, BodivaMonthlyAggregate, BodivaQuarterlyAggregate,
)

__all__ = [
    "Family",
    "User",
    "BankAccount",
    "BudgetCategory",
    "TransactionManual",
    "BankStatement",
    "ConciliationLog",
    "MarketNews",
    "Broker",
    "Instrument",
    "Portfolio",
    "PortfolioHolding",
    "Trade",
    "BrokerFileUpload",
    "WatchlistItem",
    "MarketSnapshot",
    "OrderBookSnapshot",
    "BondMaster",
    "ImportLog",
    "YieldCurveHistory",
    "IncomeEvent",
    "BodivaMonthlyAggregate",
    "BodivaQuarterlyAggregate",
]
