"""
Tabela de Posições (Holdings).
Individual instrument positions within a portfolio.
"""
from sqlalchemy import Column, ForeignKey, Numeric, Integer, Date
from app.database import Base
from app.utils.base import BaseMixin


class PortfolioHolding(Base, BaseMixin):
    __tablename__ = "portfolio_holdings"

    portfolio_id = Column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    instrument_id = Column(
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    )
    broker_id = Column(
        ForeignKey("brokers.id", ondelete="SET NULL"),
        nullable=True,
    )

    quantity = Column(Integer, nullable=False, default=0)         # Number of units
    avg_buy_price = Column(Numeric(15, 2), nullable=False)        # Preço médio de compra
    current_price = Column(Numeric(15, 2), nullable=True)         # Preço atual de mercado
    current_value = Column(Numeric(15, 2), nullable=True)         # quantity * current_price
    unrealized_pnl = Column(Numeric(15, 2), nullable=True)        # Gain/loss unrealizado
    unrealized_pnl_pct = Column(Numeric(7, 2), nullable=True)     # % gain/loss

    # Next coupon projection
    next_coupon_date = Column(Date, nullable=True)
    next_coupon_amount = Column(Numeric(15, 2), nullable=True)
