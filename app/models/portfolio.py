"""
Tabela de Carteiras (Portfolios).
Users can have multiple portfolios (real + simulated) scoped by family.
"""
import enum
from sqlalchemy import Column, String, ForeignKey, Numeric, Boolean
from app.database import Base
from app.utils.base import BaseMixin


class PortfolioType(str, enum.Enum):
    REAL = "REAL"
    SIMULATED = "SIMULATED"


class Portfolio(Base, BaseMixin):
    __tablename__ = "portfolios"

    family_id = Column(
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String(100), nullable=False)          # e.g. "High Yield", "Reforma"
    description = Column(String(255), nullable=True)
    portfolio_type = Column(String(20), default="REAL", nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    # Performance snapshot (updated periodically)
    total_invested = Column(Numeric(15, 2), default=0, nullable=False)
    current_value = Column(Numeric(15, 2), default=0, nullable=False)
    total_return_pct = Column(Numeric(7, 2), default=0, nullable=False)  # % gain/loss
