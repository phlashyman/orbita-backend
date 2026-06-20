"""
Pares de moeda — taxas de câmbio actualizadas automaticamente.
Para Angola: USD/AOA, EUR/AOA, ZAR/AOA, EUR/USD.

As taxas são actualizadas por um job APScheduler (diário).
"""
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, UniqueConstraint
from app.database import Base
from app.utils.base import BaseMixin


class CurrencyPair(Base, BaseMixin):
    """
    Taxa de câmbio para um par de moedas num dado momento.
    """
    __tablename__ = "currency_pairs"
    __table_args__ = (
        UniqueConstraint("pair", "snapshot_date", name="uq_currency_pair_date"),
    )

    # Par: "USD/AOA", "EUR/AOA", "ZAR/AOA", "EUR/USD"
    pair = Column(String(7), nullable=False, index=True)

    # Taxas
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    mid = Column(Float, nullable=False, comment="(bid + ask) / 2, ou rate única")

    # Variação
    variation_pct = Column(Float, nullable=True)

    # Fonte
    source = Column(String(50), default="bna", comment="bna / serpapi / manual")

    # Timestamp do snapshot
    snapshot_date = Column(DateTime, nullable=False, default=datetime.utcnow)
