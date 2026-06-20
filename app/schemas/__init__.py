"""
Orbita Pydantic schemas — exported for easy import.
All schemas follow Pydantic v2 patterns with SQLAlchemy compatibility.
"""

from app.schemas.family import FamilyCreate, FamilyRead
from app.schemas.user import (
    Token,
    TokenData,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.schemas.bank_account import (
    BankAccountCreate,
    BankAccountRead,
    BankAccountUpdate,
)
from app.schemas.budget_category import (
    BudgetCategoryCreate,
    BudgetCategoryRead,
    BudgetCategoryUpdate,
    BudgetSummary,
    CategorySpent,
)
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListFilter,
    TransactionRead,
    TransactionUpdate,
)
from app.schemas.bank_statement import (
    BankStatementImport,
    BankStatementLine,
    BankStatementRead,
    StatementStatusUpdate,
)
from app.schemas.conciliation import (
    MatchRequest,
    MatchResult,
    MatchScore,
    UnmatchRequest,
)
from app.schemas.receipt import ReceiptUploadResponse
from app.schemas.market_news import (
    MarketNewsCreate,
    MarketNewsRead,
    MarketNewsListItem,
    MarketNewsUpdate,
    MarketNewsStatusUpdate,
    NewsGenerateRequest,
    NewsGenerateResponse,
)
from app.schemas.portfolio import (
    BrokerCreate,
    BrokerRead,
    BrokerUpdate,
    ConsolidatedPortfolioSummary,
    HoldingWithDetails,
    InstrumentCreate,
    InstrumentRead,
    InstrumentUpdate,
    PortfolioCreate,
    PortfolioHoldingCreate,
    PortfolioHoldingRead,
    PortfolioHoldingUpdate,
    PortfolioRead,
    PortfolioSummary,
    PortfolioUpdate,
    TradeCreate,
    TradeRead,
)
from app.schemas.broker_file import (
    BrokerFileImportRequest,
    BrokerFileImportResult,
    BrokerFileProcessResult,
    BrokerFileUploadCreate,
    BrokerFileUploadListItem,
    BrokerFileUploadRead,
    BrokerFileUploadUpdate,
    BrokerPositionExtracted,
)

__all__ = [
    # family
    "FamilyCreate",
    "FamilyRead",
    # user
    "UserCreate",
    "UserRead",
    "UserLogin",
    "Token",
    "TokenData",
    # bank_account
    "BankAccountCreate",
    "BankAccountRead",
    "BankAccountUpdate",
    # budget_category
    "BudgetCategoryCreate",
    "BudgetCategoryRead",
    "BudgetCategoryUpdate",
    "BudgetSummary",
    "CategorySpent",
    # transaction
    "TransactionCreate",
    "TransactionRead",
    "TransactionUpdate",
    "TransactionListFilter",
    # bank_statement
    "BankStatementLine",
    "BankStatementImport",
    "BankStatementRead",
    "StatementStatusUpdate",
    # conciliation
    "MatchRequest",
    "MatchResult",
    "MatchScore",
    "UnmatchRequest",
    # receipt
    "ReceiptUploadResponse",
    # market_news
    "MarketNewsCreate",
    "MarketNewsRead",
    "MarketNewsListItem",
    "MarketNewsUpdate",
    "MarketNewsStatusUpdate",
    "NewsGenerateRequest",
    "NewsGenerateResponse",
    # portfolio
    "BrokerCreate",
    "BrokerRead",
    "BrokerUpdate",
    "InstrumentCreate",
    "InstrumentRead",
    "InstrumentUpdate",
    "PortfolioCreate",
    "PortfolioRead",
    "PortfolioUpdate",
    "PortfolioHoldingCreate",
    "PortfolioHoldingRead",
    "PortfolioHoldingUpdate",
    "TradeCreate",
    "TradeRead",
    "PortfolioSummary",
    "ConsolidatedPortfolioSummary",
    "HoldingWithDetails",
    # broker_file
    "BrokerFileUploadCreate",
    "BrokerFileUploadRead",
    "BrokerFileUploadListItem",
    "BrokerFileUploadUpdate",
    "BrokerFileProcessResult",
    "BrokerFileImportRequest",
    "BrokerFileImportResult",
    "BrokerPositionExtracted",
]
