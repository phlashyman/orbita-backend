"""
Pydantic schemas for Portfolio module.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Broker Schemas
# ============================================================================

class BrokerCreate(BaseModel):
    name: str = Field(..., max_length=100)
    full_name: Optional[str] = Field(None, max_length=200)
    code: str = Field(..., max_length=20)
    is_active: bool = True


class BrokerRead(BaseModel):
    id: UUID
    name: str
    full_name: Optional[str]
    code: str
    is_active: bool

    class Config:
        from_attributes = True


class BrokerUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    full_name: Optional[str] = Field(None, max_length=200)
    code: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


# ============================================================================
# Instrument Schemas
# ============================================================================

class InstrumentCreate(BaseModel):
    isin: str = Field(..., max_length=12)
    ticker: str = Field(..., max_length=20)
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    instrument_type: str = "TREASURY_BOND"
    issuer: str = Field(..., max_length=100)
    face_value: Decimal
    coupon_rate: Optional[Decimal] = None
    interest_type: str = "FIXED"
    issue_date: date
    maturity_date: date
    frequency_months: int = 12
    current_price: Optional[Decimal] = None
    current_yield: Optional[Decimal] = None
    withholding_tax: Decimal = Decimal("10.00")
    is_active: bool = True
    currency: str = "AOA"


class InstrumentRead(BaseModel):
    id: UUID
    isin: str
    ticker: str
    name: str
    description: Optional[str]
    instrument_type: str
    issuer: str
    face_value: Decimal
    coupon_rate: Optional[Decimal]
    interest_type: str
    issue_date: date
    maturity_date: date
    frequency_months: int
    current_price: Optional[Decimal]
    current_yield: Optional[Decimal]
    withholding_tax: Decimal
    is_active: bool
    currency: str

    class Config:
        from_attributes = True


class InstrumentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    current_price: Optional[Decimal] = None
    current_yield: Optional[Decimal] = None
    is_active: Optional[bool] = None


# ============================================================================
# Portfolio Schemas
# ============================================================================

class PortfolioCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    portfolio_type: str = "REAL"
    is_default: bool = False


class PortfolioRead(BaseModel):
    id: UUID
    family_id: UUID
    user_id: Optional[UUID]
    name: str
    description: Optional[str]
    portfolio_type: str
    is_default: bool
    total_invested: Decimal
    current_value: Decimal
    total_return_pct: Decimal
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PortfolioUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    is_default: Optional[bool] = None


# ============================================================================
# PortfolioHolding Schemas
# ============================================================================

class PortfolioHoldingCreate(BaseModel):
    portfolio_id: UUID
    instrument_id: UUID
    broker_id: Optional[UUID] = None
    quantity: int = Field(..., gt=0)
    avg_buy_price: Decimal = Field(..., gt=0)


class PortfolioHoldingRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    instrument_id: Optional[UUID] = None
    instrument_ticker: Optional[str] = None
    instrument_name: Optional[str] = None
    instrument_type: Optional[str] = None
    broker_id: Optional[UUID]
    broker_name: Optional[str] = None
    quantity: int
    avg_buy_price: Decimal
    current_price: Optional[Decimal]
    current_value: Optional[Decimal]
    unrealized_pnl: Optional[Decimal]
    unrealized_pnl_pct: Optional[Decimal]
    next_coupon_date: Optional[date]
    next_coupon_amount: Optional[Decimal]

    class Config:
        from_attributes = True


class PortfolioHoldingUpdate(BaseModel):
    quantity: Optional[int] = Field(None, gt=0)
    avg_buy_price: Optional[Decimal] = Field(None, gt=0)
    broker_id: Optional[UUID] = None


# ============================================================================
# Trade Schemas
# ============================================================================

class TradeCreate(BaseModel):
    portfolio_id: UUID
    holding_id: Optional[UUID] = None
    instrument_id: Optional[UUID] = None
    broker_id: Optional[UUID] = None
    trade_type: str  # BUY, SELL, COUPON, MATURITY
    trade_date: date
    quantity: int = 0
    price: Decimal
    total_amount: Decimal
    fees: Decimal = Decimal("0")
    notes: Optional[str] = None


class TradeRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    holding_id: Optional[UUID]
    instrument_id: Optional[UUID]
    instrument_ticker: Optional[str] = None
    broker_id: Optional[UUID]
    broker_name: Optional[str] = None
    trade_type: str
    trade_date: date
    quantity: int
    price: Decimal
    total_amount: Decimal
    fees: Decimal
    notes: Optional[str]
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# Portfolio Summary / Dashboard
# ============================================================================

class PortfolioSummary(BaseModel):
    portfolio_id: UUID
    portfolio_name: str
    total_invested: Decimal
    current_value: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    holdings_count: int
    yield_weighted: Optional[Decimal]
    next_coupon_total: Optional[Decimal]
    next_coupon_date: Optional[date]


class ConsolidatedPortfolioSummary(BaseModel):
    family_id: UUID
    total_portfolios: int
    total_invested: Decimal
    current_value: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    total_holdings: int
    weighted_yield: Optional[Decimal]
    portfolio_breakdown: List[PortfolioSummary]


class HoldingWithDetails(BaseModel):
    holding: PortfolioHoldingRead
    trades: List[TradeRead]
    instrument: Optional[InstrumentRead] = None
