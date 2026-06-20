"""
Tabela de Operações (Trades).
Transaction history for portfolio holdings (buy/sell/coupon).
"""
import enum
from sqlalchemy import Column, ForeignKey, Numeric, Date, String, Integer
from app.database import Base
from app.utils.base import BaseMixin


class TradeType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    COUPON = "COUPON"       # Interest payment received
    MATURITY = "MATURITY"   # Principal repayment at maturity


class Trade(Base, BaseMixin):
    __tablename__ = "trades"

    portfolio_id = Column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    holding_id = Column(
        ForeignKey("portfolio_holdings.id", ondelete="SET NULL"),
        nullable=True,
    )
    instrument_id = Column(
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    )
    broker_id = Column(
        ForeignKey("brokers.id", ondelete="SET NULL"),
        nullable=True,
    )

    trade_type = Column(String(20), nullable=False)       # BUY, SELL, COUPON, MATURITY
    trade_date = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    price = Column(Numeric(15, 2), nullable=False)        # Price per unit
    total_amount = Column(Numeric(15, 2), nullable=False) # quantity * price
    fees = Column(Numeric(10, 2), default=0, nullable=False)  # Broker fees
    notes = Column(String(255), nullable=True)
