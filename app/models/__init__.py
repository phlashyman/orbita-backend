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

# === NOVOS MODELS DE INVESTIMENTO (Sprint 3) ===
from app.models.investor_profile import InvestorProfile
from app.models.portfolio_analytics import PortfolioAnalytics
from app.models.scenario_analysis import ScenarioAnalysis
from app.models.scenario_definition import ScenarioDefinition
from app.models.investment_signal import InvestmentSignal
from app.models.investment_goal import InvestmentGoal
from app.models.ai_assistant_log import AIAssistantLog
from app.models.educational_content_view import EducationalContentView
from app.models.currency_pair import CurrencyPair
from app.models.international_position import InternationalPosition
from app.models.market_comparison import MarketComparison
from app.models.country_risk_metric import CountryRiskMetric
from app.models.tax_rule import TaxRule

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
    # Novos modelos de investimento
    "InvestorProfile",
    "PortfolioAnalytics",
    "ScenarioAnalysis",
    "ScenarioDefinition",
    "InvestmentSignal",
    "InvestmentGoal",
    "AIAssistantLog",
    "EducationalContentView",
    "CurrencyPair",
    "InternationalPosition",
    "MarketComparison",
    "CountryRiskMetric",
    "TaxRule",
]
