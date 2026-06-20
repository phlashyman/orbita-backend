"""
Posições internacionais declaradas pelo utilizador.
Representa investimentos em mercados estrangeiros (S&P 500, JSE, STOXX, etc.)
que o utilizador detém fora da BODIVA.
"""
from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, JSON
from app.database import Base
from app.utils.base import BaseMixin


class InternationalPosition(Base, BaseMixin):
    """
    Posição internacional declarada.
    Pode ser importada manualmente ou via SerpAPI futuramente.
    """
    __tablename__ = "international_positions"

    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Identificação do activo
    ticker = Column(String(20), nullable=False, comment="AAPL, VOO, NPN.JSE")
    exchange = Column(String(20), nullable=True, comment="NASDAQ, NYSE, JSE, LSE")
    name = Column(String(200), nullable=True, comment="Apple Inc., Vanguard S&P 500 ETF")

    # Moeda e mercado
    currency = Column(String(3), default="USD")
    market = Column(String(50), nullable=True, comment="US_EQUITY, US_BOND, SA_EQUITY, EU_EQUITY, COMMODITY")

    # Quantidade e preço
    quantity = Column(Float, nullable=False)
    purchase_price = Column(Float, nullable=True)
    purchase_price_currency = Column(String(3), nullable=True)
    purchase_date = Column(Date, nullable=True)

    # Valor actual (actualizado periodicamente via SerpAPI)
    current_price = Column(Float, nullable=True)
    current_price_date = Column(Date, nullable=True)
    current_value_aoa = Column(Float, nullable=True, comment="Valor actual convertido para AOA")

    # Ganhos/perdas
    unrealized_pnl = Column(Float, nullable=True)
    unrealized_pnl_pct = Column(Float, nullable=True)

    # Metadados
    notes = Column(String(500), nullable=True)
    metadata_json = Column(JSON, nullable=True)
